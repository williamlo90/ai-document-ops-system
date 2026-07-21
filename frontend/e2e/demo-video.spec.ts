import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'
import { mkdirSync, readdirSync, renameSync, rmSync } from 'node:fs'
import path from 'node:path'

import { installPortfolioApi } from './portfolio-fixtures'

test.skip(!process.env.CAPTURE_DEMO, 'Demo recording runs only through npm run capture:demo.')
test.setTimeout(360_000)

const holdFor = (milliseconds: number) => process.env.DEMO_FAST
  ? Math.max(80, Math.round(milliseconds * 0.015))
  : milliseconds

async function ensureDemoOverlay(page: Page) {
  await page.evaluate(() => {
    if (document.getElementById('portfolio-demo-style')) return
    const style = document.createElement('style')
    style.id = 'portfolio-demo-style'
    style.textContent = `
      #portfolio-demo-caption {
        position: fixed; left: 50%; bottom: 22px; z-index: 2147483646;
        width: min(960px, calc(100vw - 64px)); transform: translateX(-50%);
        padding: 14px 20px; border: 1px solid rgba(255,255,255,.2); border-radius: 7px;
        background: rgba(7,19,41,.95); color: white; box-shadow: 0 12px 34px rgba(0,0,0,.28);
        font-family: Inter, ui-sans-serif, system-ui, sans-serif; pointer-events: none;
      }
      #portfolio-demo-caption strong { display: block; margin-bottom: 4px; color: #67e8f9; font-size: 12px; text-transform: uppercase; }
      #portfolio-demo-caption span { display: block; font-size: 18px; line-height: 1.35; }
      #portfolio-demo-cursor {
        position: fixed; z-index: 2147483647; width: 24px; height: 24px; border: 3px solid white;
        border-radius: 50%; background: rgba(0,135,155,.78); box-shadow: 0 0 0 3px rgba(0,135,155,.24);
        transform: translate(-50%,-50%); transition: left .5s ease, top .5s ease, box-shadow .2s ease;
        pointer-events: none; opacity: 0;
      }
      #portfolio-demo-cursor.pulse { box-shadow: 0 0 0 12px rgba(0,135,155,.1); }
      #portfolio-demo-title {
        position: fixed; inset: 0; z-index: 2147483645; display: flex; align-items: center; justify-content: center;
        padding: 80px; background: #071329; color: white; font-family: Inter, ui-sans-serif, system-ui, sans-serif;
        text-align: center; pointer-events: none;
      }
      #portfolio-demo-title div { max-width: 980px; }
      #portfolio-demo-title small { display: block; margin-bottom: 18px; color: #67e8f9; font-size: 15px; font-weight: 800; text-transform: uppercase; }
      #portfolio-demo-title h1 { margin: 0; font-size: 52px; line-height: 1.08; letter-spacing: 0; }
      #portfolio-demo-title p { max-width: 800px; margin: 24px auto 0; color: #cbd5e1; font-size: 23px; line-height: 1.45; }
      #portfolio-demo-title ul { display: inline-block; margin: 28px auto 0; padding-left: 24px; color: #e2e8f0; text-align: left; font-size: 20px; line-height: 1.65; }
    `
    document.head.appendChild(style)
    const caption = document.createElement('div')
    caption.id = 'portfolio-demo-caption'
    caption.style.display = 'none'
    caption.innerHTML = '<strong></strong><span></span>'
    document.body.appendChild(caption)
    const cursor = document.createElement('div')
    cursor.id = 'portfolio-demo-cursor'
    document.body.appendChild(cursor)
  })
}

async function showCaption(page: Page, label: string, text: string, hold: number) {
  await ensureDemoOverlay(page)
  await page.evaluate(({ label, text }) => {
    const caption = document.getElementById('portfolio-demo-caption')
    if (!caption) return
    caption.querySelector('strong')!.textContent = label
    caption.querySelector('span')!.textContent = text
    caption.style.display = 'block'
  }, { label, text })
  await page.waitForTimeout(holdFor(hold))
}

async function hideCaption(page: Page) {
  await page.evaluate(() => {
    const caption = document.getElementById('portfolio-demo-caption')
    if (caption) caption.style.display = 'none'
  })
}

async function showTitle(page: Page, eyebrow: string, title: string, body: string, bullets: string[], hold: number) {
  await ensureDemoOverlay(page)
  await hideCaption(page)
  await page.evaluate(({ eyebrow, title, body, bullets }) => {
    document.getElementById('portfolio-demo-title')?.remove()
    const cursor = document.getElementById('portfolio-demo-cursor')
    if (cursor) cursor.style.opacity = '0'
    const overlay = document.createElement('section')
    overlay.id = 'portfolio-demo-title'
    const content = document.createElement('div')
    const small = document.createElement('small')
    small.textContent = eyebrow
    const heading = document.createElement('h1')
    heading.textContent = title
    const paragraph = document.createElement('p')
    paragraph.textContent = body
    content.append(small, heading, paragraph)
    if (bullets.length) {
      const list = document.createElement('ul')
      for (const bullet of bullets) {
        const item = document.createElement('li')
        item.textContent = bullet
        list.appendChild(item)
      }
      content.appendChild(list)
    }
    overlay.appendChild(content)
    document.body.appendChild(overlay)
  }, { eyebrow, title, body, bullets })
  await page.waitForTimeout(holdFor(hold))
  await page.evaluate(() => document.getElementById('portfolio-demo-title')?.remove())
  await page.waitForTimeout(holdFor(700))
}

async function pointAndClick(page: Page, locator: Locator) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  if (box) {
    await page.evaluate(({ left, top }) => {
      const cursor = document.getElementById('portfolio-demo-cursor')
      if (!cursor) return
      cursor.style.left = `${left}px`
      cursor.style.top = `${top}px`
      cursor.style.opacity = '1'
    }, { left: box.x + box.width / 2, top: box.y + box.height / 2 })
    await page.waitForTimeout(holdFor(650))
  }
  await locator.click()
  await page.evaluate(() => document.getElementById('portfolio-demo-cursor')?.classList.add('pulse'))
  await page.waitForTimeout(holdFor(240))
  await page.evaluate(() => document.getElementById('portfolio-demo-cursor')?.classList.remove('pulse'))
}

async function waitForPdf(page: Page) {
  const canvas = page.locator('canvas.pdf-canvas:visible').first()
  await expect(canvas).toBeVisible({ timeout: 20_000 })
  await expect.poll(() => canvas.evaluate((element) => element.width * element.height), { timeout: 20_000 }).toBeGreaterThan(0)
  await expect(page.getByText('Loading invoice...')).toHaveCount(0, { timeout: 20_000 })
}

async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(holdFor(500))
}

async function recordDemo(browser: Browser) {
  const outputDirectory = path.resolve('../docs/assets/demo')
  const outputPath = path.join(outputDirectory, 'ai-document-ops-demo.webm')
  mkdirSync(outputDirectory, { recursive: true })
  for (const filename of readdirSync(outputDirectory)) {
    if (filename.endsWith('.webm')) rmSync(path.join(outputDirectory, filename), { force: true })
  }

  const context = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: outputDirectory, size: { width: 1280, height: 720 } },
    colorScheme: 'light',
  })
  const page = await context.newPage()
  const video = page.video()

  try {
    const fixture = await installPortfolioApi(page)
    await page.goto('/overview')
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), James/ })).toBeVisible()
    await settle(page)

    await showTitle(
      page,
      'Recruiter walkthrough',
      'AI Document Operations System',
      'Invoice reading with deterministic validation, explicit human decisions, controlled export, and evaluation-grade evidence.',
      [],
      8_000,
    )

    await showCaption(page, '1 - Business overview', 'A reviewer starts with urgent work, grounded findings, the decision queue, and current processing evidence. Every number links to its source workflow.', 13_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Invoices', exact: true }))
    await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
    await waitForPdf(page)
    await showCaption(page, '2 - Invoice library', 'The invoice library combines search, status, owner, validation findings, and an authenticated PDF preview. Upload is separate from reviewer approval.', 14_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Review Queue', exact: true }))
    await expect(page.getByRole('heading', { name: 'Review Queue', exact: true })).toBeVisible()
    await waitForPdf(page)
    await showCaption(page, '3 - Reviewer queue', 'Risk, confidence, age, owner, and the stored validation finding appear together. The selected invoice explains why human attention is required.', 14_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Review invoice', exact: true }))
    await expect(page.getByRole('heading', { name: 'Review invoice', exact: true })).toBeVisible()
    await waitForPdf(page)
    await showCaption(page, '4 - Source evidence', 'The reviewer compares the original Summit invoice with extracted values on the same screen. The PDF is rendered by the real application viewer.', 12_000)
    await showCaption(page, 'Grounded extraction', 'Invoice number, vendor, dates, totals, line items, confidence, and validation results remain inspectable. AI proposes evidence; it does not own the decision.', 12_000)
    await showCaption(page, 'Deterministic blocker', 'A missing PO policy requirement blocks approval. Correction and rejection require a note, while the backend independently refuses an unsafe approval transition.', 12_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Exceptions', exact: true }))
    await expect(page.getByRole('heading', { name: 'Exceptions', exact: true })).toBeVisible()
    await showCaption(page, '5 - Exception resolution', 'The exception workspace reconciles category totals with the underlying rows and states exactly what happened, what is required, and which check blocks approval.', 15_000)

    fixture.setRole('uploader')
    await page.goto('/invoices?invoice=doc-northstar-correction')
    await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
    await waitForPdf(page)
    await pointAndClick(page, page.getByRole('button', { name: 'Correct invoice data' }))
    await expect(page.getByRole('dialog', { name: 'Correct invoice data' })).toBeVisible()
    await showCaption(page, '6 - Reviewer correction loop', 'The uploader sees the reviewer note, changes only incorrect fields, explains the change, and sends the invoice back for revalidation and review.', 15_000)

    fixture.setRole('administrator')
    fixture.setApproved(true)
    await page.goto('/review/doc-acme')
    await expect(page.getByRole('heading', { name: 'Decision recorded', exact: true })).toBeVisible()
    await waitForPdf(page)
    await showCaption(page, '7 - Recorded consequence', 'After correction and revalidation, the recorded approval exposes actor, timestamp, audit-event count, and controlled-export eligibility. It cannot be submitted twice.', 15_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Exports', exact: true }))
    await expect(page.getByRole('heading', { name: 'Exports', exact: true })).toBeVisible()
    await showCaption(page, '8 - Controlled export', 'Only approved invoices without unresolved blockers enter a persistent batch. Idempotent execution records success or failure before invoice export state changes.', 15_000)

    await pointAndClick(page, page.getByRole('link', { name: 'Evaluation', exact: true }))
    await expect(page.getByRole('heading', { name: 'Evaluation', exact: true })).toBeVisible()
    await showCaption(page, '9 - Evaluation evidence', 'The current synthetic run reports field and validation match, regressions, scenario coverage, duration, provider calls, and estimated cost with visible claim limits.', 20_000)

    await pointAndClick(page, page.getByRole('link', { name: 'System', exact: true }))
    await expect(page.getByRole('heading', { name: 'System', exact: true })).toBeVisible()
    await showCaption(page, '10 - Operational evidence', 'A degraded export service does not make healthy upload, reading, extraction, review, or storage capabilities appear unavailable. Failures stay sanitized and retryable.', 15_000)

    await showTitle(
      page,
      'Evidence boundary',
      'What this portfolio proves',
      'A production-shaped invoice workflow with explicit safety boundaries and reproducible engineering evidence.',
      [
        '20 labeled synthetic invoice scenarios; 160/160 fields in the controlled run',
        'Deterministic validation and backend-enforced approval gates',
        'Reviewer corrections, audit consequences, export idempotency, and retry evidence',
        'Synthetic evidence is not production accuracy or measured customer impact',
      ],
      14_000,
    )
  } finally {
    await context.close()
  }

  if (!video) throw new Error('Playwright did not create a video artifact.')
  const recordedPath = await video.path()
  renameSync(recordedPath, outputPath)
  return outputPath
}

test('record current recruiter demo video', async ({ browser }) => {
  const outputPath = await recordDemo(browser)
  expect(outputPath).toContain('ai-document-ops-demo.webm')
})
