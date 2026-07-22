import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { installPortfolioApi } from './portfolio-fixtures'

test('administrator navigates the active product without full page reloads', async ({ page }) => {
  await installPortfolioApi(page)
  await page.goto('/inbox')
  await expect(page.getByRole('heading', { name: 'Inbox', exact: true })).toBeVisible()

  const marker = await page.evaluate(() => {
    const value = crypto.randomUUID()
    ;(window as typeof window & { __spaMarker?: string }).__spaMarker = value
    return value
  })
  const destinations = [
    { link: 'Invoices', heading: 'Invoices', path: '/invoices' },
    { link: 'Exports', heading: 'Exports', path: '/exports' },
    { link: 'Quality', heading: 'Quality', path: '/admin/quality' },
    { link: 'Operations', heading: 'Operations', path: '/admin/operations' },
  ]

  for (const destination of destinations) {
    if ((page.viewportSize()?.width ?? 1280) < 760) {
      await page.getByRole('button', { name: 'Open navigation' }).click()
    }
    await page.getByRole('link', { name: destination.link, exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`${destination.path.replace('/', '\\/')}(?:\\?.*)?$`))
    await expect(page.getByRole('heading', { name: destination.heading, exact: true }).first()).toBeVisible()
    await expect.poll(() => page.evaluate(() => (window as typeof window & { __spaMarker?: string }).__spaMarker)).toBe(marker)
  }
})

test('uploader sees only invoice intake and lifecycle work', async ({ page }) => {
  await installPortfolioApi(page, 'uploader')
  await page.goto('/')
  await expect(page).toHaveURL(/\/invoices$/)
  await expect(page.getByRole('link', { name: 'Invoices', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Inbox', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Exports', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Quality', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Operations', exact: true })).toHaveCount(0)
})

test('reviewer sees decision work but not administrator areas', async ({ page }) => {
  await installPortfolioApi(page, 'reviewer')
  await page.goto('/')
  await expect(page).toHaveURL(/\/inbox$/)
  await expect(page.getByRole('link', { name: 'Inbox', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Invoices', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Exports', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Quality', exact: true })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Operations', exact: true })).toHaveCount(0)
})

test('legacy product URLs redirect to the corresponding current view', async ({ page }) => {
  await installPortfolioApi(page)
  await page.goto('/review-queue?risk=high')
  await expect(page).toHaveURL(/\/inbox\?risk=high&state=needs-decision|\/inbox\?state=needs-decision&risk=high/)
  await page.goto('/exceptions?category=duplicate')
  await expect(page).toHaveURL(/\/inbox\?category=duplicate&state=blocked|\/inbox\?state=blocked&category=duplicate/)
  await page.goto('/evaluation')
  await expect(page).toHaveURL(/\/admin\/quality$/)
  await page.goto('/system')
  await expect(page).toHaveURL(/\/admin\/operations$/)
})

test('active product pages have no serious accessibility violations or page overflow', async ({ page }) => {
  await installPortfolioApi(page)
  const pages = [
    { path: '/inbox', heading: 'Inbox' },
    { path: '/invoices', heading: 'Invoices' },
    { path: '/review/doc-acme', heading: 'Review invoice' },
    { path: '/exports', heading: 'Exports' },
    { path: '/admin/quality', heading: 'Quality' },
    { path: '/admin/operations', heading: 'Operations' },
  ]

  for (const current of pages) {
    await page.goto(current.path)
    await expect(page.getByRole('heading', { name: current.heading, exact: true }).first()).toBeVisible()
    const results = await new AxeBuilder({ page }).exclude('canvas').analyze()
    expect(results.violations.filter((item) => ['serious', 'critical'].includes(item.impact ?? '')), current.path).toEqual([])
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, current.path).toBeLessThanOrEqual(1)
  }
})

test('mobile navigation opens and closes without shifting the document', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'Mobile-only interaction.')
  await installPortfolioApi(page)
  await page.goto('/inbox')
  const before = await page.evaluate(() => document.documentElement.scrollWidth)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('button', { name: 'Dismiss navigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Close navigation' }).click()
  await expect(page.getByRole('button', { name: 'Dismiss navigation' })).toHaveCount(0)
  const after = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(after).toBe(before)
})
