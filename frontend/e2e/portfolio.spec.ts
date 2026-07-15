import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

test.skip(!process.env.CAPTURE_PORTFOLIO, 'Portfolio capture runs only through npm run capture:portfolio.')
test.setTimeout(90_000)

const now = '2026-07-15T03:00:00Z'
const cleanDocument = documentSummary('doc-clean', 'summit-industrial-parts.pdf', false)
const duplicateDocument = documentSummary('doc-duplicate', 'summit-industrial-parts-copy.pdf', true)
const cleanItem = workItem('item-clean', cleanDocument, false)
const duplicateItem = workItem('item-duplicate', duplicateDocument, true)

function documentSummary(id: string, filename: string, blocked: boolean) {
  return {
    id,
    filename,
    original_filename: filename,
    status: 'needs_review',
    created_at: now,
    document_type: 'invoice',
    supported_extraction_schema: 'invoice_v1',
    vendor_name: 'Summit Industrial Parts',
    total: '704.00',
    currency: 'USD',
    validation_issue_count: blocked ? 1 : 0,
    validation_error_count: blocked ? 1 : 0,
    has_validation_errors: blocked,
    validation_codes: blocked ? ['duplicate_invoice'] : [],
  }
}

function workItem(id: string, document: ReturnType<typeof documentSummary>, blocked: boolean) {
  return {
    id,
    title: `Invoice Review - ${document.vendor_name}`,
    work_type: 'invoice_review',
    priority: blocked ? 'high' : 'normal',
    status: blocked ? 'blocked' : 'awaiting_human',
    linked_document_ids: [document.id],
    business_context: {
      vendor_name: document.vendor_name,
      total: document.total,
      currency: document.currency,
      requested_outcome: 'Check invoice data and record a reviewer decision.',
    },
    created_at: now,
    updated_at: now,
    current_plan_id: null,
    assignee: 'Finance reviewer',
    requested_outcome: 'Check invoice data and record a reviewer decision.',
    tags: blocked ? ['invoice', 'duplicate'] : ['invoice'],
    plans: [],
    current_plan: null,
    drafts: [],
    approvals: [],
    policy_decisions: [],
    activity: [],
  }
}

function extraction(blocked: boolean) {
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
      line_items: [{ description: 'Industrial parts', quantity: '4', unit_price: '160.00', amount: '640.00' }],
    },
    confidence: [
      { field_name: 'vendor_name', score: 0.98, source_page: 1, source_text: 'Vendor: Summit Industrial Parts' },
      { field_name: 'invoice_number', score: 0.97, source_page: 1, source_text: 'Invoice SIP-7788' },
      { field_name: 'total', score: 0.99, source_page: 1, source_text: 'Total USD 704.00' },
    ],
    validation: blocked
      ? [{ field_name: 'invoice_number', message: 'Possible duplicate invoice for this vendor and invoice number.', severity: 'error', code: 'duplicate_invoice' }]
      : [],
  }
}

async function mockPortfolioApi(page: Page) {
  const cleanPdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf'))
  const duplicatePdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_copy.pdf'))
  await page.route('**/*', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    if (pathname === '/auth/session') return route.fulfill({ json: { authenticated: true, actor: 'portfolio-reviewer' } })
    if (pathname === '/backoffice/workspace') {
      return route.fulfill({
        json: {
          workspace_id: 'portfolio',
          work_items: [cleanItem, duplicateItem],
          pending_approvals: [],
          documents: [cleanDocument, duplicateDocument],
          metrics: { work_items: 2, pending_approvals: 1, drafts: 0, policy_decisions: 0 },
        },
      })
    }
    if (pathname === '/invoices') {
      return route.fulfill({
        json: {
          items: [
            { ...cleanDocument, business_status: 'needs_review', current_stage: 'needs_review' },
            { ...duplicateDocument, business_status: 'needs_correction', current_stage: 'needs_attention' },
          ],
          page: 1,
          page_size: 100,
          total: 2,
          total_pages: 1,
        },
      })
    }
    if (pathname === '/operations/notifications') return route.fulfill({ json: { notifications: [], unread_count: 0 } })
    if (pathname === '/providers/health') return route.fulfill({ json: { overall_status: 'healthy', providers: [] } })
    if (pathname === '/operations/jobs') return route.fulfill({ json: { worker: { status: 'healthy', queued_jobs: 0, failed_jobs: 0, stalled_jobs: 0, evidence: 'Ready' }, failed_jobs: [] } })
    if (pathname === `/backoffice/work-items/${cleanItem.id}`) return route.fulfill({ json: { work_item: cleanItem } })
    if (pathname === `/backoffice/work-items/${duplicateItem.id}`) return route.fulfill({ json: { work_item: duplicateItem } })
    if (pathname === `/documents/${cleanDocument.id}`) return route.fulfill({ json: { document: cleanDocument, extraction: extraction(false), audit_events: [] } })
    if (pathname === `/documents/${duplicateDocument.id}`) return route.fulfill({ json: { document: duplicateDocument, extraction: extraction(true), audit_events: [] } })
    if (pathname === `/documents/${cleanDocument.id}/content`) return route.fulfill({ contentType: 'application/pdf', body: cleanPdf })
    if (pathname === `/documents/${duplicateDocument.id}/content`) return route.fulfill({ contentType: 'application/pdf', body: duplicatePdf })
    return route.continue()
  })
}

async function waitForPdf(page: Page) {
  const canvas = page.locator('canvas.pdf-canvas')
  await expect(canvas).toBeVisible()
  await expect.poll(() => canvas.evaluate((element) => element.width * element.height)).toBeGreaterThan(0)
  await expect(page.getByText('Loading invoice...')).toHaveCount(0, { timeout: 20_000 })
}

test('capture current uploader and reviewer workflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await mockPortfolioApi(page)
  const output = path.resolve('../docs/assets/screenshots')

  await page.addInitScript(() => localStorage.setItem('docops-role', 'intake'))
  await page.goto('/')
  await page.getByRole('button', { name: 'My Invoices' }).click()
  await expect(page.getByRole('heading', { name: 'My Invoices', level: 2 })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'uploader-invoices.png'), fullPage: true })

  await page.locator('select.role-select').selectOption('administrator')
  await expect(page.getByRole('heading', { name: 'Approvals' }).first()).toBeVisible()
  await expect(page.getByText('Waiting decision (1)')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'reviewer-approvals.png'), fullPage: true })

  await page.getByRole('button', { name: /summit-industrial-parts\.pdf/i }).click()
  await expect(page.getByText('Choose the outcome for this invoice')).toBeVisible()
  await waitForPdf(page)
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await waitForPdf(page)
  await page.screenshot({ path: path.join(output, 'reviewer-decision.png') })

  await page.locator('.pager button').last().click()
  await expect(page.getByText('summit-industrial-parts-copy.pdf').first()).toBeVisible()
  await expect(page.getByText('must be resolved before approval')).toBeVisible()
  await waitForPdf(page)
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await waitForPdf(page)
  await expect(page.getByRole('button', { name: 'Approve' })).toBeDisabled()
  await page.screenshot({ path: path.join(output, 'blocked-duplicate.png') })
})
