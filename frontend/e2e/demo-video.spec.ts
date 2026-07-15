import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'
import { mkdirSync, readFileSync, readdirSync, renameSync, rmSync } from 'node:fs'
import path from 'node:path'

test.skip(!process.env.CAPTURE_DEMO, 'Demo recording runs only through npm run capture:demo.')
test.setTimeout(300_000)

const createdAt = '2026-07-15T03:00:00Z'
const cleanId = 'demo-clean-invoice'
const duplicateId = 'demo-duplicate-invoice'
const cleanItemId = 'demo-clean-review'
const duplicateItemId = 'demo-duplicate-review'
const holdFor = (milliseconds: number) => process.env.DEMO_FAST ? Math.max(80, Math.round(milliseconds * 0.02)) : milliseconds

type InvoiceKind = 'clean' | 'duplicate'

type DemoState = {
  uploadCount: number
  uploaded: Record<InvoiceKind, boolean>
  processed: Record<InvoiceKind, boolean>
  submitted: Record<InvoiceKind, boolean>
  approved: boolean
}

function documentFor(kind: InvoiceKind, state: DemoState) {
  const isDuplicate = kind === 'duplicate'
  const processed = state.processed[kind]
  const approved = kind === 'clean' && state.approved
  return {
    id: isDuplicate ? duplicateId : cleanId,
    filename: isDuplicate ? 'summit-industrial-parts-copy.pdf' : 'summit-industrial-parts.pdf',
    original_filename: isDuplicate ? 'summit-industrial-parts-copy.pdf' : 'summit-industrial-parts.pdf',
    status: approved ? 'approved' : processed ? 'needs_review' : 'queued',
    created_at: createdAt,
    document_type: 'invoice',
    supported_extraction_schema: 'invoice_v1',
    vendor_name: 'Summit Industrial Parts',
    total: '704.00',
    currency: 'USD',
    validation_issue_count: processed && isDuplicate ? 1 : 0,
    validation_error_count: processed && isDuplicate ? 1 : 0,
    has_validation_errors: processed && isDuplicate,
    validation_codes: processed && isDuplicate ? ['duplicate_invoice'] : [],
  }
}

function extractionFor(kind: InvoiceKind) {
  const isDuplicate = kind === 'duplicate'
  return {
    document_type: 'invoice',
    schema_version: 'invoice_v1',
    data: {
      vendor_name: 'Summit Industrial Parts',
      invoice_number: 'SIP-7788',
      invoice_date: '2026-07-16',
      due_date: '2026-08-15',
      subtotal: '640.00',
      tax: '64.00',
      total: '704.00',
      currency: 'USD',
      line_items: [
        { description: 'Industrial parts', quantity: '4', unit_price: '160.00', amount: '640.00' },
      ],
    },
    confidence: [
      { field_name: 'vendor_name', score: 0.98, source_page: 1, source_text: 'Vendor: Summit Industrial Parts' },
      { field_name: 'invoice_number', score: 0.97, source_page: 1, source_text: 'Invoice SIP-7788' },
      { field_name: 'invoice_date', score: 0.96, source_page: 1, source_text: 'Invoice date 16 July 2026' },
      { field_name: 'due_date', score: 0.95, source_page: 1, source_text: 'Due date 15 August 2026' },
      { field_name: 'subtotal', score: 0.98, source_page: 1, source_text: 'Subtotal USD 640.00' },
      { field_name: 'tax', score: 0.98, source_page: 1, source_text: 'Tax USD 64.00' },
      { field_name: 'total', score: 0.99, source_page: 1, source_text: 'Total USD 704.00' },
      { field_name: 'currency', score: 0.99, source_page: 1, source_text: 'USD' },
    ],
    validation: isDuplicate
      ? [{ field_name: 'invoice_number', message: 'Possible duplicate invoice for this vendor and invoice number.', severity: 'error', code: 'duplicate_invoice' }]
      : [],
  }
}

function workItemFor(kind: InvoiceKind, state: DemoState) {
  const isDuplicate = kind === 'duplicate'
  const approved = kind === 'clean' && state.approved
  const document = documentFor(kind, state)
  return {
    id: isDuplicate ? duplicateItemId : cleanItemId,
    title: `Invoice Review - ${document.vendor_name}`,
    work_type: 'invoice_review',
    priority: isDuplicate ? 'high' : 'normal',
    status: approved ? 'completed' : isDuplicate ? 'blocked' : 'awaiting_human',
    linked_document_ids: [document.id],
    business_context: {
      vendor_name: document.vendor_name,
      total: document.total,
      currency: document.currency,
      requested_outcome: 'Check invoice data and record a reviewer decision.',
    },
    created_at: createdAt,
    updated_at: createdAt,
    current_plan_id: `plan-${kind}`,
    assignee: 'Finance reviewer',
    requested_outcome: 'Check invoice data and record a reviewer decision.',
    tags: isDuplicate ? ['invoice', 'duplicate'] : ['invoice'],
    plans: [],
    current_plan: null,
    drafts: [],
    approvals: [],
    policy_decisions: [],
    activity: approved
      ? [{ id: 'approval-event', event_type: 'invoice_approved', actor: 'portfolio-reviewer', created_at: createdAt }]
      : [],
  }
}

function uploadedKinds(state: DemoState) {
  return (['clean', 'duplicate'] as InvoiceKind[]).filter((kind) => state.uploaded[kind])
}

function submittedKinds(state: DemoState) {
  return (['clean', 'duplicate'] as InvoiceKind[]).filter((kind) => state.submitted[kind])
}

async function delay(milliseconds: number) {
  await new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function mockDemoApi(page: Page, state: DemoState) {
  const cleanPdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf'))
  const duplicatePdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_copy.pdf'))

  await page.route('**/*', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    const method = request.method()

    if (pathname === '/auth/session') {
      return route.fulfill({ json: { authenticated: true, actor: 'portfolio-reviewer' } })
    }
    if (pathname === '/documents/upload-policy') {
      return route.fulfill({ json: { max_upload_bytes: 15 * 1024 * 1024, duplicates: [] } })
    }
    if (pathname === '/documents/upload' && method === 'POST') {
      const kind: InvoiceKind = state.uploadCount === 0 ? 'clean' : 'duplicate'
      state.uploadCount += 1
      state.uploaded[kind] = true
      await delay(900)
      return route.fulfill({ json: { document: documentFor(kind, state) } })
    }
    if (pathname === `/documents/${cleanId}/process` && method === 'POST') {
      await delay(1_800)
      state.processed.clean = true
      return route.fulfill({ json: { document: documentFor('clean', state) } })
    }
    if (pathname === `/documents/${duplicateId}/process` && method === 'POST') {
      await delay(1_800)
      state.processed.duplicate = true
      return route.fulfill({ json: { document: documentFor('duplicate', state) } })
    }
    if (pathname === `/documents/${cleanId}`) {
      return route.fulfill({
        json: {
          document: documentFor('clean', state),
          extraction: state.processed.clean ? extractionFor('clean') : null,
          audit_events: state.processed.clean
            ? [
              { id: 'clean-uploaded', event_type: 'document_uploaded', created_at: createdAt },
              { id: 'clean-processed', event_type: 'processing_succeeded', created_at: createdAt },
              ...(state.approved ? [{ id: 'clean-approved', event_type: 'invoice_approved', created_at: createdAt, actor: 'portfolio-reviewer' }] : []),
            ]
            : [{ id: 'clean-uploaded', event_type: 'document_uploaded', created_at: createdAt }],
        },
      })
    }
    if (pathname === `/documents/${duplicateId}`) {
      return route.fulfill({
        json: {
          document: documentFor('duplicate', state),
          extraction: state.processed.duplicate ? extractionFor('duplicate') : null,
          audit_events: state.processed.duplicate
            ? [
              { id: 'duplicate-uploaded', event_type: 'document_uploaded', created_at: createdAt },
              { id: 'duplicate-processed', event_type: 'processing_succeeded', created_at: createdAt },
            ]
            : [{ id: 'duplicate-uploaded', event_type: 'document_uploaded', created_at: createdAt }],
        },
      })
    }
    if (pathname === `/documents/${cleanId}/content`) {
      return route.fulfill({ contentType: 'application/pdf', body: cleanPdf })
    }
    if (pathname === `/documents/${duplicateId}/content`) {
      return route.fulfill({ contentType: 'application/pdf', body: duplicatePdf })
    }
    if (/^\/invoices\/[^/]+\/draft$/.test(pathname) && method === 'POST') {
      return route.fulfill({ json: { status: 'saved' } })
    }
    if (pathname === '/backoffice/work-items' && method === 'POST') {
      const payload = request.postDataJSON() as { linked_document_ids: string[] }
      const kind: InvoiceKind = payload.linked_document_ids[0] === duplicateId ? 'duplicate' : 'clean'
      state.submitted[kind] = true
      return route.fulfill({ status: 201, json: { work_item: workItemFor(kind, state) } })
    }
    if (/^\/backoffice\/work-items\/[^/]+\/plan$/.test(pathname) && method === 'POST') {
      const kind: InvoiceKind = pathname.includes(duplicateItemId) ? 'duplicate' : 'clean'
      return route.fulfill({ json: { work_item: workItemFor(kind, state) } })
    }
    if (pathname === `/backoffice/work-items/${cleanItemId}` && method === 'GET') {
      return route.fulfill({ json: { work_item: workItemFor('clean', state) } })
    }
    if (pathname === `/backoffice/work-items/${duplicateItemId}` && method === 'GET') {
      return route.fulfill({ json: { work_item: workItemFor('duplicate', state) } })
    }
    if (pathname === `/review/${cleanId}/approve` && method === 'POST') {
      await delay(1_200)
      state.approved = true
      return route.fulfill({ json: { status: 'approved', actor: 'portfolio-reviewer', reviewed_at: createdAt } })
    }
    if (pathname === '/backoffice/workspace') {
      const documents = uploadedKinds(state).map((kind) => documentFor(kind, state))
      const workItems = submittedKinds(state).map((kind) => workItemFor(kind, state))
      return route.fulfill({
        json: {
          workspace_id: 'portfolio-demo',
          work_items: workItems,
          pending_approvals: [],
          documents,
          metrics: {
            work_items: workItems.length,
            pending_approvals: workItems.filter((item) => item.status === 'awaiting_human').length,
            drafts: 0,
            policy_decisions: 0,
          },
        },
      })
    }
    if (pathname === '/invoices') {
      const items = uploadedKinds(state).map((kind) => {
        const document = documentFor(kind, state)
        return {
          ...document,
          business_status: document.status === 'approved' ? 'approved' : kind === 'duplicate' && state.processed.duplicate ? 'needs_correction' : 'needs_review',
          current_stage: document.status === 'approved' ? 'completed' : kind === 'duplicate' && state.processed.duplicate ? 'needs_attention' : 'needs_review',
        }
      })
      return route.fulfill({ json: { items, page: 1, page_size: 100, total: items.length, total_pages: 1 } })
    }
    if (pathname === '/operations/notifications') {
      return route.fulfill({ json: { notifications: [], unread_count: 0 } })
    }
    if (pathname === '/providers/health') {
      return route.fulfill({ json: { overall_status: 'healthy', providers: [] } })
    }
    if (pathname === '/operations/jobs') {
      return route.fulfill({ json: { worker: { status: 'healthy', queued_jobs: 0, failed_jobs: 0, stalled_jobs: 0, evidence: 'Ready' }, failed_jobs: [] } })
    }
    return route.continue()
  })
}

async function waitForPdf(page: Page) {
  const canvas = page.locator('canvas.pdf-canvas')
  await expect(canvas).toBeVisible()
  await expect.poll(() => canvas.evaluate((element) => element.width * element.height)).toBeGreaterThan(0)
  await expect(page.getByText('Loading invoice...')).toHaveCount(0, { timeout: 20_000 })
}

async function ensureDemoOverlay(page: Page) {
  await page.evaluate(() => {
    if (document.getElementById('portfolio-demo-style')) return
    const style = document.createElement('style')
    style.id = 'portfolio-demo-style'
    style.textContent = `
      #portfolio-demo-caption {
        position: fixed; left: 50%; bottom: 22px; z-index: 2147483646;
        width: min(920px, calc(100vw - 64px)); transform: translateX(-50%);
        padding: 14px 20px; border: 1px solid rgba(255,255,255,.2); border-radius: 8px;
        background: rgba(7, 19, 41, .94); color: white; box-shadow: 0 12px 34px rgba(0,0,0,.28);
        font-family: Inter, ui-sans-serif, system-ui, sans-serif; pointer-events: none;
      }
      #portfolio-demo-caption strong { display: block; color: #5eead4; font-size: 12px; text-transform: uppercase; margin-bottom: 4px; }
      #portfolio-demo-caption span { display: block; font-size: 19px; line-height: 1.35; }
      #portfolio-demo-cursor {
        position: fixed; z-index: 2147483647; width: 24px; height: 24px; border: 3px solid white;
        border-radius: 50%; background: rgba(13, 148, 136, .75); box-shadow: 0 0 0 3px rgba(13,148,136,.28);
        transform: translate(-50%, -50%); transition: left .55s ease, top .55s ease, box-shadow .2s ease;
        pointer-events: none; opacity: 0;
      }
      #portfolio-demo-cursor.pulse { box-shadow: 0 0 0 12px rgba(13,148,136,.08); }
      #portfolio-demo-title {
        position: fixed; inset: 0; z-index: 2147483645; display: flex; align-items: center; justify-content: center;
        padding: 80px; background: #071329; color: white; font-family: Inter, ui-sans-serif, system-ui, sans-serif;
        text-align: center; pointer-events: none;
      }
      #portfolio-demo-title div { max-width: 940px; }
      #portfolio-demo-title small { display: block; color: #5eead4; font-size: 15px; font-weight: 800; text-transform: uppercase; margin-bottom: 18px; }
      #portfolio-demo-title h1 { margin: 0; font-size: 52px; line-height: 1.08; letter-spacing: 0; }
      #portfolio-demo-title p { margin: 24px auto 0; max-width: 780px; color: #cbd5e1; font-size: 24px; line-height: 1.45; }
      #portfolio-demo-title ul { display: inline-block; margin: 28px auto 0; padding-left: 24px; color: #e2e8f0; text-align: left; font-size: 21px; line-height: 1.65; }
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

async function showCaption(page: Page, label: string, text: string, hold = 5_000) {
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

async function showTitle(page: Page, eyebrow: string, title: string, body: string, bullets: string[] = [], hold = 7_000) {
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
      bullets.forEach((bullet) => {
        const item = document.createElement('li')
        item.textContent = bullet
        list.appendChild(item)
      })
      content.appendChild(list)
    }
    overlay.appendChild(content)
    document.body.appendChild(overlay)
  }, { eyebrow, title, body, bullets })
  await page.waitForTimeout(holdFor(hold))
  await page.evaluate(() => document.getElementById('portfolio-demo-title')?.remove())
  await page.waitForTimeout(700)
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
    await page.waitForTimeout(750)
  }
  await locator.click()
  await page.evaluate(() => document.getElementById('portfolio-demo-cursor')?.classList.add('pulse'))
  await page.waitForTimeout(250)
  await page.evaluate(() => document.getElementById('portfolio-demo-cursor')?.classList.remove('pulse'))
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
  const state: DemoState = {
    uploadCount: 0,
    uploaded: { clean: false, duplicate: false },
    processed: { clean: false, duplicate: false },
    submitted: { clean: false, duplicate: false },
    approved: false,
  }

  try {
    await mockDemoApi(page, state)
    await page.addInitScript(() => localStorage.setItem('docops-role', 'intake'))
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Upload and check an invoice' })).toBeVisible()

    await showTitle(
      page,
      'Recruiter demo',
      'AI Document Operations System',
      'Evidence-bound invoice extraction, deterministic validation, and human approval.',
      [],
      8_000,
    )

    await showCaption(page, '1 - Upload', 'An intake operator starts with one PDF invoice. The business workflow stays simple and visible.', 7_000)
    const cleanPdfPath = path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf')
    await page.locator('input[type="file"]').setInputFiles(cleanPdfPath)
    await waitForPdf(page)
    await showCaption(page, 'Source evidence', 'The original PDF is visible before processing. The user never has to trust extracted text in isolation.', 8_000)

    await pointAndClick(page, page.getByRole('main').getByRole('button', { name: 'Upload Invoice' }))
    await expect(page.getByRole('button', { name: 'Read Invoice Data' })).toBeVisible()
    await showCaption(page, 'Controlled intake', 'Upload creates a queued document. It does not approve the invoice or trigger an external action.', 6_000)

    await pointAndClick(page, page.getByRole('button', { name: 'Read Invoice Data' }))
    await expect(page.getByRole('heading', { name: 'Check invoice data' })).toBeVisible({ timeout: 20_000 })
    await waitForPdf(page)
    await showCaption(page, 'AI extraction', 'OCR and the extraction model propose invoice fields. Confidence and source snippets remain attached to the result.', 10_000)
    await showCaption(page, 'Deterministic checks', 'Arithmetic validation confirms that subtotal plus tax equals total before the invoice can move forward.', 8_000)

    await pointAndClick(page, page.getByRole('button', { name: 'Continue' }))
    await expect(page.getByRole('heading', { name: 'Summit Industrial Parts' })).toBeVisible()
    await showCaption(page, 'Explicit handoff', 'The uploader sends one review item. The reviewer still owns the business decision.', 7_000)
    await pointAndClick(page, page.getByRole('button', { name: 'Send for Review' }))
    await expect(page.getByRole('heading', { name: 'Invoice is waiting for approval' })).toBeVisible()
    await showCaption(page, 'No auto-approval', 'The clean invoice is waiting for a separate reviewer. High confidence never bypasses the human gate.', 9_000)

    await pointAndClick(page, page.locator('select.role-select'))
    await page.locator('select.role-select').selectOption('administrator')
    await expect(page.getByRole('heading', { name: 'Approvals' }).first()).toBeVisible()
    await showCaption(page, '2 - Human review', 'The reviewer queue shows only invoices that need a decision, correction, or follow-up.', 9_000)

    await pointAndClick(page, page.getByRole('button', { name: /summit-industrial-parts\.pdf/i }))
    await expect(page.getByText('Choose the outcome for this invoice')).toBeVisible()
    await waitForPdf(page)
    await page.getByRole('button', { name: 'Zoom out' }).click()
    await waitForPdf(page)
    await showCaption(page, 'Evidence beside decision', 'The reviewer compares the PDF, key fields, and validation result on one screen.', 12_000)
    await page.getByPlaceholder('Example: Total and vendor match the PDF.').fill('Vendor, invoice number, and total match the PDF.')
    await showCaption(page, 'Human authority', 'Approval is an explicit reviewer action. The model cannot press this button.', 6_000)
    await pointAndClick(page, page.getByRole('button', { name: 'Approve' }))
    await expect(page.getByText('This invoice has been approved.')).toBeVisible({ timeout: 15_000 })
    await showCaption(page, 'Decision recorded', 'The document now shows Approved. The backend also records the actor, timestamp, and audit event.', 9_000)

    await page.locator('select.role-select').selectOption('intake')
    await expect(page.getByRole('heading', { name: 'Upload and check an invoice' })).toBeVisible()
    await showTitle(
      page,
      'Failure-mode demo',
      'What happens when the invoice is a duplicate?',
      'The same workflow now receives a second PDF with the same vendor and invoice number.',
      [],
      7_000,
    )

    const duplicatePdfPath = path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_copy.pdf')
    await page.locator('input[type="file"]').setInputFiles(duplicatePdfPath)
    await waitForPdf(page)
    await showCaption(page, '3 - Upload duplicate', 'The second document looks valid on its own, so the system must compare it with prior invoice data.', 7_000)
    await pointAndClick(page, page.getByRole('main').getByRole('button', { name: 'Upload Invoice' }))
    await expect(page.getByRole('button', { name: 'Read Invoice Data' })).toBeVisible()
    await pointAndClick(page, page.getByRole('button', { name: 'Read Invoice Data' }))
    await expect(page.getByRole('heading', { name: 'Check invoice data' })).toBeVisible({ timeout: 20_000 })
    await waitForPdf(page)
    await showCaption(page, 'Cross-document validation', 'A deterministic duplicate check flags the repeated vendor and invoice number as a blocking error.', 12_000)

    await pointAndClick(page, page.getByRole('button', { name: 'Continue' }))
    await showCaption(page, 'Safe routing', 'The invoice can be sent to a reviewer for correction or rejection, but the blocker remains attached.', 7_000)
    await pointAndClick(page, page.getByRole('button', { name: 'Send for Review' }))
    await expect(page.getByRole('heading', { name: 'Invoice is waiting for approval' })).toBeVisible()
    await showCaption(page, 'Exception preserved', 'The system does not hide the failure or silently mark the duplicate as complete.', 7_000)

    await page.locator('select.role-select').selectOption('administrator')
    await expect(page.getByRole('heading', { name: 'Approvals' }).first()).toBeVisible()
    await pointAndClick(page, page.getByRole('button', { name: 'Needs correction (1)' }))
    await expect(page.getByRole('button', { name: /summit-industrial-parts-copy\.pdf/i })).toBeVisible()
    await showCaption(page, 'Reviewer exception queue', 'The duplicate appears under Needs correction instead of blending into the clean approval queue.', 9_000)

    await pointAndClick(page, page.getByRole('button', { name: /summit-industrial-parts-copy\.pdf/i }))
    await expect(page.getByText('must be resolved before approval')).toBeVisible()
    await waitForPdf(page)
    await page.getByRole('button', { name: 'Zoom out' }).click()
    await waitForPdf(page)
    await expect(page.getByRole('button', { name: 'Approve' })).toBeDisabled()
    await showCaption(page, 'Approval blocked', 'Approve is disabled. The reviewer can request correction or reject, but cannot override the validation blocker.', 13_000)
    await showCaption(page, 'Safety boundary', 'AI proposes fields. Deterministic code enforces business rules. A human owns the final decision.', 9_000)

    await showTitle(
      page,
      'Evidence summary',
      'What this portfolio proves',
      'A reproducible, provider-backed document workflow with explicit limits.',
      [
        '20 synthetic invoice scenarios and 160/160 expected fields',
        'Human approval required before a document is approved',
        'Duplicate invoices are blocked by deterministic validation',
        'Synthetic evidence is not a claim of measured customer impact',
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

test('record recruiter demo video', async ({ browser }) => {
  const outputPath = await recordDemo(browser)
  expect(outputPath).toContain('ai-document-ops-demo.webm')
})
