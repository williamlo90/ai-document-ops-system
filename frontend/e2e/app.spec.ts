import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const workspace = {
  workspace_id: 'e2e',
  work_items: [],
  pending_approvals: [],
  documents: [],
  metrics: { work_items: 0, pending_approvals: 0, drafts: 0, policy_decisions: 0 },
}

async function mockApi(
  page: Page,
  options: { workspaceFailure?: boolean; role?: 'reviewer' | 'uploader' } = {},
) {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/auth/session') {
      const role = options.role ?? 'reviewer'
      await route.fulfill({
        json: {
          authenticated: true,
          actor: role === 'uploader' ? 'e2e-uploader' : 'e2e-reviewer',
          user_id: role === 'uploader' ? 'user-uploader' : 'user-reviewer',
          workspace_id: 'e2e',
          role,
          is_admin: role === 'reviewer',
        },
      })
      return
    }
    if (url.pathname === '/backoffice/workspace') {
      if (options.workspaceFailure) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Provider unavailable"}' })
      } else {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(workspace) })
      }
      return
    }
    if (url.pathname === '/operations/notifications') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"notifications":[],"unread_count":0}' })
      return
    }
    if (url.pathname === '/providers/health') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"overall_status":"healthy","providers":[]}' })
      return
    }
    if (url.pathname === '/operations/jobs') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"worker":{"status":"healthy"},"jobs":[]}' })
      return
    }
    if (url.pathname === '/invoices') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[],"page":1,"page_size":100,"total":0,"total_pages":1}' })
      return
    }
    await route.continue()
  })
}

test('reviewer opens the simplified approval area', async ({ page }) => {
  await mockApi(page, { role: 'reviewer' })
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Approvals' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /^Upload$/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Approvals' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Invoices' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'History' })).toHaveCount(0)

  const openNavigation = page.getByRole('button', { name: 'Open navigation' })
  if (await openNavigation.isVisible()) await openNavigation.click()
  await page.getByRole('button', { name: 'Approvals' }).click()
  await expect(page.getByText('No invoices waiting for approval')).toBeVisible()
})

test('failure path presents a recoverable workspace error', async ({ page }) => {
  await mockApi(page, { workspaceFailure: true })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Unable to load workspace' })).toBeVisible()
  await expect(page.getByText(/could not reach the invoice workspace/i)).toBeVisible()
  await expect(page.getByText(/technical detail is available/i)).toBeVisible()
  await expect(page.getByText('Provider unavailable')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Retry' })).toBeEnabled()
})

test('intake screen has no serious automated accessibility violations', async ({ page }) => {
  await mockApi(page, { role: 'uploader' })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /upload and check an invoice/i })).toBeVisible()
  const results = await new AxeBuilder({ page }).exclude('iframe').analyze()
  expect(results.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact ?? ''))).toEqual([])
})

test('responsive shell does not create page-level horizontal overflow', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  const openNavigation = page.getByRole('button', { name: 'Open navigation' })
  if (await openNavigation.isVisible()) {
    await openNavigation.click()
    await expect(page.getByRole('button', { name: 'Close menu' })).toBeVisible()
  } else {
    await expect(page.locator('aside.sidebar')).toBeVisible()
  }
})

test('laptop layout remains usable at 125, 150, and 200 percent zoom', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'desktop', 'Zoom matrix is exercised once in the desktop project.')
  await mockApi(page, { role: 'uploader' })
  for (const zoom of [1.25, 1.5, 2]) {
    await page.setViewportSize({ width: Math.floor(1366 / zoom), height: Math.floor(768 / zoom) })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /upload and check an invoice/i })).toBeVisible()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, `page overflow at ${zoom * 100}% zoom`).toBeLessThanOrEqual(1)
  }
})
