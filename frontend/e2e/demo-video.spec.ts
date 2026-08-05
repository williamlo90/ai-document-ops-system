import { expect, test, type Browser, type Page } from '@playwright/test'
import { mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs'
import path from 'node:path'

import { installPortfolioApi } from './portfolio-fixtures'

test.skip(!process.env.CAPTURE_DEMO, 'Demo recording runs only through npm run capture:demo.')
test.setTimeout(240_000)

const hold = (milliseconds: number) =>
  process.env.DEMO_FAST ? Math.max(100, Math.round(milliseconds * 0.02)) : milliseconds

async function installOverlay(page: Page) {
  await page.evaluate(() => {
    const style = document.createElement('style')
    style.textContent = `
      #demo-caption { position: fixed; left: 50%; bottom: 22px; z-index: 2147483646; width: min(900px,calc(100vw - 56px)); transform: translateX(-50%); padding: 14px 20px; border-radius: 6px; color: #fff; background: rgba(7,19,41,.96); box-shadow: 0 12px 32px rgba(0,0,0,.25); pointer-events: none; }
      #demo-caption strong { display: block; margin-bottom: 4px; color: #70d6df; font-size: 13px; }
      #demo-caption span { display: block; font-size: 18px; line-height: 1.4; }
      #demo-title { position: fixed; inset: 0; z-index: 2147483645; display: grid; place-items: center; padding: 72px; color: #fff; background: #071329; text-align: center; pointer-events: none; }
      #demo-title div { max-width: 900px; } #demo-title small { color: #70d6df; font-size: 15px; font-weight: 700; }
      #demo-title img { display: block; width: 58px; height: 58px; margin: 0 auto 20px; }
      #demo-title h1 { margin: 14px 0; font-size: 54px; letter-spacing: 0; } #demo-title p { margin: 0; color: #cbd5e1; font-size: 23px; line-height: 1.45; }
    `
    document.head.appendChild(style)
    const caption = document.createElement('div')
    caption.id = 'demo-caption'
    caption.style.display = 'none'
    caption.innerHTML = '<strong></strong><span></span>'
    document.body.appendChild(caption)
  })
}

async function caption(page: Page, label: string, body: string, milliseconds = 10_000) {
  await page.evaluate(
    ({ label, body }) => {
      const element = document.getElementById('demo-caption')
      if (!element) return
      element.querySelector('strong')!.textContent = label
      element.querySelector('span')!.textContent = body
      element.style.display = 'block'
    },
    { label, body },
  )
  await page.waitForTimeout(hold(milliseconds))
}

async function title(page: Page) {
  await page.evaluate(() => {
    const overlay = document.createElement('section')
    overlay.id = 'demo-title'
    overlay.innerHTML =
      '<div><img src="/favicon.svg" alt=""><small>Accounts payable workflow</small><h1>AI-Powered Invoice Review &amp; Approval System</h1><p>Source comparison, deterministic validation, explicit human decisions, and controlled export.</p></div>'
    document.body.appendChild(overlay)
  })
  await page.waitForTimeout(hold(9_000))
  await page.evaluate(() => document.getElementById('demo-title')?.remove())
}

async function visit(page: Page, route: string, heading: string) {
  await page.goto(route)
  await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible()
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(hold(700))
}

async function waitForPdf(page: Page) {
  const canvas = page.locator('canvas.pdf-canvas:visible').first()
  await expect(canvas).toBeVisible({ timeout: 20_000 })
  await expect
    .poll(() => canvas.evaluate((element) => element.width * element.height), { timeout: 20_000 })
    .toBeGreaterThan(0)
}

async function record(browser: Browser) {
  const outputDirectory = path.resolve('../docs/assets/demo')
  const outputPath = path.join(outputDirectory, 'invoice-review-demo.webm')
  mkdirSync(outputDirectory, { recursive: true })
  for (const filename of readdirSync(outputDirectory)) {
    if (filename.endsWith('.webm')) rmSync(path.join(outputDirectory, filename), { force: true })
  }

  const context = await browser.newContext({
    viewport: { width: 1440, height: 810 },
    recordVideo: { dir: outputDirectory, size: { width: 1280, height: 720 } },
    colorScheme: 'light',
  })
  const page = await context.newPage()
  const video = page.video()

  try {
    await installPortfolioApi(page)
    await visit(page, '/inbox?state=needs-decision', 'Inbox')
    await installOverlay(page)
    await title(page)
    await caption(
      page,
      '1. Work that needs attention',
      'Inbox separates reviewer decisions from blocking issues. It does not select or change an invoice until the user opens it.',
    )

    await visit(page, '/review/doc-acme', 'Review invoice')
    await installOverlay(page)
    await waitForPdf(page)
    await page.getByRole('button', { name: 'View source for Total amount' }).click()
    await expect(page.getByText('98% confidence / Page 1')).toBeVisible()
    await caption(
      page,
      '2. Source, fields, and checks together',
      'The reviewer compares the PDF with extracted fields and exact source evidence. The displayed total conflicts with subtotal plus tax, so deterministic validation blocks approval.',
    )

    await visit(page, '/invoices?invoice=doc-northstar-correction', 'Invoices')
    await installOverlay(page)
    await caption(
      page,
      '3. One invoice lifecycle',
      'Invoices provides upload, status, correction context, and document inspection without duplicating the review queue.',
    )

    await visit(page, '/exports?status=in_batch&batch=batch-july', 'Exports')
    await installOverlay(page)
    await caption(
      page,
      '4. Controlled export',
      'Only approved and eligible invoices enter an export batch. Eligibility and idempotency remain enforced by the server.',
    )

    await visit(page, '/admin/quality?run=eval-7', 'Quality')
    await installOverlay(page)
    await caption(
      page,
      '5. Bounded quality evidence',
      'Labeled synthetic results show field and validation match together with dataset limits. They are engineering evidence, not a production-accuracy claim.',
    )

    await visit(page, '/admin/operations', 'Operations')
    await installOverlay(page)
    await caption(
      page,
      '6. Actionable operations',
      'Administrators see unresolved alerts, failed jobs, retry eligibility, service state, and audit records without exposing credentials or raw provider responses.',
    )

    await page.evaluate(() => {
      const element = document.getElementById('demo-caption')
      if (element) element.style.display = 'none'
      const overlay = document.createElement('section')
      overlay.id = 'demo-title'
      overlay.innerHTML =
        '<div><small>Evidence boundary</small><h1>Human-controlled invoice review</h1><p>This demo proves the workflow and safeguards. It does not claim customer impact, production accuracy, or readiness for real client data.</p></div>'
      document.body.appendChild(overlay)
    })
    await page.waitForTimeout(hold(9_000))
  } finally {
    await page.close()
    await context.close()
  }

  const generated = await video?.path()
  if (!generated) throw new Error('Playwright did not create a demo video.')
  if (path.resolve(generated) !== path.resolve(outputPath)) renameSync(generated, outputPath)
  return outputPath
}

test('record current Invoice Review demo', async ({ browser }) => {
  const outputPath = await record(browser)
  expect(outputPath).toContain('invoice-review-demo.webm')
})
