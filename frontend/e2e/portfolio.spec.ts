import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

import { installPortfolioApi } from './portfolio-fixtures'

test.skip(!process.env.CAPTURE_PORTFOLIO, 'Portfolio capture runs only through npm run capture:portfolio.')
test.setTimeout(180_000)
test.describe.configure({ mode: 'serial' })

const viewports = [
  { name: 'desktop', width: 1536, height: 1024 },
  { name: 'compact', width: 1280, height: 800 },
  { name: 'tablet', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
] as const

const pages = [
  { name: 'overview', route: '/overview', heading: /Good (morning|afternoon|evening), James/ },
  { name: 'invoices', route: '/invoices?invoice=doc-acme', heading: 'Invoices', pdf: true },
  { name: 'review-queue', route: '/review-queue?invoice=doc-acme', heading: 'Review Queue', pdf: true },
  { name: 'review-workspace', route: '/review/doc-acme', heading: 'Review invoice', pdf: true },
  { name: 'exceptions', route: '/exceptions?exception=exception-doc-acme', heading: 'Exceptions' },
  { name: 'exports', route: '/exports?status=ready&batch=batch-july', heading: 'Exports' },
  { name: 'evaluation', route: '/evaluation?run=eval-7&range=10', heading: 'Evaluation' },
  { name: 'system', route: '/system', heading: 'System' },
] as const

for (const viewport of viewports) {
  test(`archive approved pages at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const fixture = await installPortfolioApi(page)
    const output = viewport.name === 'desktop'
      ? path.resolve('../docs/assets/screenshots')
      : path.resolve(`../docs/assets/screenshots/${viewport.name}`)

    for (const target of pages) {
      const route = viewport.width < 1180 ? unselectedRoute(target.name, target.route) : target.route
      await page.goto(route)
      await expect(page.getByRole('heading', { name: target.heading, exact: typeof target.heading === 'string' }).first()).toBeVisible()
      if (target.pdf && route.includes('doc-')) await waitForVisiblePdf(page)
      await settle(page)
      await expectNoPageOverflow(page)
      await page.screenshot({ path: path.join(output, `${target.name}.png`), fullPage: true })

      if (viewport.name === 'desktop' && target.name === 'review-workspace') {
        await page.screenshot({ path: path.join(output, 'reviewer-decision.png'), fullPage: true })
      }
    }

    if (viewport.name !== 'desktop') return

    fixture.setApproved(true)
    await page.goto('/review/doc-acme')
    await expect(page.getByRole('heading', { name: 'Decision recorded', exact: true })).toBeVisible()
    await waitForVisiblePdf(page)
    await settle(page)
    await page.screenshot({ path: path.join(output, 'approved-decision.png'), fullPage: true })

    fixture.setRole('uploader')
    await page.goto('/invoices?invoice=doc-northstar-correction')
    await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
    await waitForVisiblePdf(page)
    await page.getByRole('button', { name: 'Correct invoice data' }).click()
    await expect(page.getByRole('dialog', { name: 'Correct invoice data' })).toBeVisible()
    await settle(page)
    await page.screenshot({ path: path.join(output, 'uploader-correction.png'), fullPage: true })
  })
}

async function waitForVisiblePdf(page: Page) {
  const canvas = page.locator('canvas.pdf-canvas:visible').first()
  await expect(canvas).toBeVisible({ timeout: 20_000 })
  await expect.poll(() => canvas.evaluate((element) => element.width * element.height), { timeout: 20_000 }).toBeGreaterThan(0)
  await expect(page.getByText('Loading invoice...')).toHaveCount(0, { timeout: 20_000 })
}

async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(180)
}

async function expectNoPageOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
}

function unselectedRoute(name: string, route: string) {
  if (name === 'invoices') return '/invoices'
  if (name === 'review-queue') return '/review-queue'
  if (name === 'exceptions') return '/exceptions'
  return route
}
