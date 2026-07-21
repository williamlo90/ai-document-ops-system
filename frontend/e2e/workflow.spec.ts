import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const now = '2026-07-21T03:00:00Z'
const documentId = 'doc-1'

type FlowState = {
  correctionRequested: boolean
  correctionSubmitted: boolean
  approved: boolean
  vendorName: string
}

type RecordedCall = {
  method: string
  path: string
  body: Record<string, unknown>
}

function invoice(state: FlowState) {
  const needsCorrection = state.correctionRequested && !state.correctionSubmitted
  return {
    id: documentId,
    original_filename: 'acme-logistics.pdf',
    submitted_by: 'e2e-uploader',
    status: state.approved ? 'approved' : 'needs_review',
    business_status: state.approved ? 'approved' : needsCorrection ? 'needs_correction' : 'needs_review',
    current_stage: state.approved ? 'completed' : needsCorrection ? 'correction_requested' : 'waiting_approval',
    current_owner: needsCorrection ? 'Uploader' : 'Reviewer',
    vendor_name: state.vendorName,
    invoice_number: 'INV-001',
    invoice_date: '2026-06-18',
    due_date: '2026-07-18',
    total: '110.00',
    currency: 'USD',
    created_at: now,
    updated_at: now,
    validation_issue_count: 0,
    validation_error_count: 0,
    validation_codes: [],
    has_validation_errors: false,
    export_state: state.approved ? 'eligible' : 'not_eligible',
    work_item_id: 'item-1',
    correction_reason: needsCorrection ? 'Use the full legal vendor name shown on the PDF.' : null,
  }
}

function extraction(state: FlowState) {
  return {
    data: {
      vendor_name: state.vendorName,
      invoice_number: 'INV-001',
      invoice_date: '2026-06-18',
      due_date: '2026-07-18',
      subtotal: '100.00',
      tax: '10.00',
      total: '110.00',
      currency: 'USD',
      line_items: [],
    },
    validation: [],
    confidence: [
      { field_name: 'vendor_name', score: 0.98, source_page: 1, source_text: 'Acme Logistics' },
      { field_name: 'total', score: 0.99, source_page: 1, source_text: 'Total 110.00' },
    ],
  }
}

async function mockWorkflow(page: Page, state: FlowState, calls: RecordedCall[], role: 'reviewer' | 'uploader') {
  const pdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf'))

  await page.route('**/*', async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    const method = request.method()

    if (pathname === '/auth/session') {
      await route.fulfill({ json: {
        authenticated: true,
        actor: role === 'uploader' ? 'E2E Uploader' : 'E2E Reviewer',
        user_id: role === 'uploader' ? 'e2e-uploader' : 'e2e-reviewer',
        workspace_id: 'e2e',
        role,
        is_admin: false,
      } })
      return
    }
    if (request.resourceType() === 'document') {
      await route.continue()
      return
    }
    if (pathname === '/backoffice/workspace') {
      await route.fulfill({ json: { workspace_id: 'e2e', work_items: [], pending_approvals: [], documents: [invoice(state)], metrics: {} } })
      return
    }
    if (pathname === '/invoices' && method === 'GET') {
      const item = invoice(state)
      await route.fulfill({ json: {
        items: [item], page: 1, page_size: 10, total: 1, total_pages: 1,
        summary: {
          all: 1,
          waiting_review: item.business_status === 'needs_review' ? 1 : 0,
          needs_correction: item.business_status === 'needs_correction' ? 1 : 0,
          approved: item.business_status === 'approved' ? 1 : 0,
          exported: 0,
        },
        insights: { flagged: 0, duplicates_suspected: 0, tax_amount_issues: 0 },
      } })
      return
    }
    if (pathname === `/documents/${documentId}` && method === 'GET') {
      await route.fulfill({ json: {
        document: invoice(state),
        extraction: extraction(state),
        correction_summary: state.correctionSubmitted ? {
          latest_change_count: 1,
          latest_changed_fields: ['vendor_name'],
          latest_actor: 'E2E Uploader',
          latest_reason: 'Matched the legal name on the PDF.',
        } : null,
        audit_events: state.approved ? [{
          id: 'audit-approved', event_type: 'document_approved', actor: 'E2E Reviewer',
          old_status: 'needs_review', new_status: 'approved', created_at: now,
        }] : [],
      } })
      return
    }
    if (pathname === `/documents/${documentId}/workflow` && method === 'GET') {
      const needsCorrection = state.correctionRequested && !state.correctionSubmitted
      await route.fulfill({ json: {
        current_stage: state.approved ? 'completed' : needsCorrection ? 'correction_requested' : 'waiting_approval',
        current_owner: needsCorrection ? 'Uploader' : 'Reviewer',
        waiting_for: state.approved ? null : needsCorrection ? 'Uploader correction' : 'Reviewer decision',
        next_action: state.approved ? 'No action needed' : needsCorrection ? 'Correct invoice data' : 'Review invoice',
        attention_reason: needsCorrection ? 'Use the full legal vendor name shown on the PDF.' : null,
        work_item: { assignee: needsCorrection ? 'Uploader' : 'Finance reviewer', business_context: {} },
      } })
      return
    }
    if (pathname === `/documents/${documentId}/content`) {
      await route.fulfill({ contentType: 'application/pdf', body: pdf })
      return
    }
    if (pathname === `/invoices/${documentId}/request-correction` && method === 'POST') {
      state.correctionRequested = true
      calls.push({ method, path: pathname, body: request.postDataJSON() })
      await route.fulfill({ json: { status: 'correction_requested' } })
      return
    }
    if (pathname === `/invoices/${documentId}/draft` && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      state.vendorName = String(body.vendor_name)
      state.correctionSubmitted = true
      calls.push({ method, path: pathname, body })
      await route.fulfill({ json: { correction_recorded: true } })
      return
    }
    if (pathname === `/review/${documentId}/approve` && method === 'POST') {
      state.approved = true
      calls.push({ method, path: pathname, body: {} })
      await route.fulfill({ json: {
        document: { id: documentId, status: 'approved', updated_at: now },
        review_task: { status: 'approved', reviewer_notes: '', reviewed_by: 'E2E Reviewer', reviewed_at: now },
        decision: { status: 'approved', actor: 'E2E Reviewer', recorded_at: now, note: '', audit_event_count: 1, export_eligibility: 'eligible' },
      } })
      return
    }

    await route.continue()
  })
}

async function openDecisionPanel(page: Page) {
  const trigger = page.getByRole('button', { name: 'Open decision panel' })
  if (await trigger.isVisible()) await trigger.click()
  await expect(page.getByLabel('Reviewer decision')).toBeVisible()
}

async function confirmDialog(page: Page, name: 'Request correction' | 'Approve') {
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name, exact: true }).click()
}

test('reviewer requests a correction with a durable note', async ({ page }) => {
  const state: FlowState = { correctionRequested: false, correctionSubmitted: false, approved: false, vendorName: 'Acme Logistics' }
  const calls: RecordedCall[] = []
  await mockWorkflow(page, state, calls, 'reviewer')
  await page.goto(`/review/${documentId}`)
  await expect(page.getByRole('heading', { name: 'Review invoice', exact: true })).toBeVisible()
  await openDecisionPanel(page)

  await page.getByPlaceholder('Explain the decision for the audit trail...').fill('Use the full legal vendor name shown on the PDF.')
  await page.getByLabel('Reviewer decision').getByRole('button', { name: 'Request correction', exact: true }).click()
  await confirmDialog(page, 'Request correction')

  await expect(page.getByRole('status')).toContainText('Correction requested and recorded.')
  await expect.poll(() => calls.length).toBe(1)
  expect(calls[0]).toEqual({
    method: 'POST',
    path: `/invoices/${documentId}/request-correction`,
    body: { reason: 'Use the full legal vendor name shown on the PDF.' },
  })
})

test('uploader sees the reviewer note, corrects the data, and sends it back', async ({ page }) => {
  const state: FlowState = { correctionRequested: true, correctionSubmitted: false, approved: false, vendorName: 'Acme Logistics' }
  const calls: RecordedCall[] = []
  await mockWorkflow(page, state, calls, 'uploader')
  await page.goto(`/invoices?invoice=${documentId}`)
  await expect(page.getByRole('heading', { name: 'Invoices', exact: true })).toBeVisible()
  await expect(page.getByText('Use the full legal vendor name shown on the PDF.')).toBeVisible()

  await page.getByRole('button', { name: 'Correct invoice data' }).click()
  const dialog = page.getByRole('dialog', { name: 'Correct invoice data' })
  await dialog.getByRole('textbox', { name: 'Vendor', exact: true }).fill('Acme Logistics Ltd')
  await dialog.getByRole('textbox', { name: 'What did you change?' }).fill('Matched the legal name on the PDF.')
  await dialog.getByRole('button', { name: 'Send to reviewer' }).click()

  await expect(page.getByRole('status')).toContainText('Correction sent back to the reviewer.')
  await expect.poll(() => calls.length).toBe(1)
  expect(calls[0].body.vendor_name).toBe('Acme Logistics Ltd')
  expect(calls[0].body.correction_reason).toBe('Matched the legal name on the PDF.')
})

test('reviewer sees correction evidence before approving', async ({ page }) => {
  const state: FlowState = { correctionRequested: true, correctionSubmitted: true, approved: false, vendorName: 'Acme Logistics Ltd' }
  const calls: RecordedCall[] = []
  await mockWorkflow(page, state, calls, 'reviewer')
  await page.goto(`/review/${documentId}`)

  await expect(page.getByText('1 field corrected by E2E Uploader')).toBeVisible()
  await expect(page.getByText(/vendor name\. Matched the legal name on the PDF\./i)).toBeVisible()
  await openDecisionPanel(page)
  await page.getByLabel('Reviewer decision').getByRole('button', { name: 'Approve', exact: true }).click()
  await confirmDialog(page, 'Approve')

  await expect(page.getByRole('status')).toContainText('Invoice approved and recorded.')
  await expect(page.getByRole('heading', { name: 'Decision recorded' })).toBeVisible()
  await expect.poll(() => calls.some((call) => call.path === `/review/${documentId}/approve`)).toBe(true)
})
