import { expect, test, type Page } from '@playwright/test'

const now = '2026-06-30T10:00:00Z'

type FlowState = {
  correctionRequested: boolean
  correctionSubmitted: boolean
  approved: boolean
}

type RecordedCall = {
  method: string
  path: string
  body: Record<string, unknown>
}

const extraction = {
  document_type: 'invoice',
  schema_version: 'invoice_v1',
  data: {
    vendor_name: 'Acme Logistics',
    invoice_number: 'INV-001',
    invoice_date: '2026-06-18',
    due_date: '2026-07-18',
    subtotal: '90.00',
    tax: '10.00',
    total: '100.00',
    currency: 'USD',
    line_items: [],
  },
  validation: [],
  confidence: [],
}

function currentDocument(state: FlowState) {
  return {
    id: 'doc-1',
    filename: 'acme.pdf',
    original_filename: 'acme.pdf',
    status: state.approved ? 'approved' : 'needs_review',
    document_type: 'invoice',
    supported_extraction_schema: 'invoice_v1',
    created_at: now,
    updated_at: now,
  }
}

function currentWorkItem(state: FlowState) {
  return {
    id: 'item-1',
    title: 'Review Acme Logistics invoice',
    work_type: 'invoice_review',
    priority: 'normal',
    status: state.approved ? 'completed' : 'planning',
    linked_document_ids: ['doc-1'],
    business_context: state.correctionRequested && !state.correctionSubmitted
      ? { correction_state: 'requested', correction_reason: 'Use the full legal vendor name.' }
      : {},
    created_at: now,
    updated_at: now,
    current_plan_id: null,
    assignee: state.correctionRequested && !state.correctionSubmitted ? 'Uploader' : 'Finance reviewer',
    requested_outcome: 'Review the invoice safely',
    tags: [],
  }
}

function correctionSummary(state: FlowState) {
  if (!state.correctionSubmitted) return null
  return {
    event_count: 1,
    latest_change_count: 1,
    latest_changed_fields: ['vendor_name'],
    latest_actor: 'e2e-uploader',
    latest_reason: 'Used the legal vendor name.',
    latest_at: now,
  }
}

async function mockBusinessFlow(page: Page, state: FlowState, calls: RecordedCall[], role: 'administrator' | 'intake') {
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const document = currentDocument(state)
    const item = currentWorkItem(state)
    const itemDetail = {
      ...item,
      plans: [],
      current_plan: null,
      drafts: [],
      approvals: [],
      policy_decisions: [],
      activity: [],
    }

    if (path === '/auth/session') {
      const sessionRole = role === 'intake' ? 'uploader' : 'reviewer'
      return route.fulfill({
        json: {
          authenticated: true,
          actor: role === 'intake' ? 'e2e-uploader' : 'e2e-reviewer',
          user_id: role === 'intake' ? 'user-uploader' : 'user-reviewer',
          workspace_id: 'e2e',
          role: sessionRole,
          is_admin: role === 'administrator',
        },
      })
    }
    if (path === '/operations/notifications') return route.fulfill({ json: { notifications: [], unread_count: 0 } })
    if (path === '/providers/health') return route.fulfill({ json: { overall_status: 'healthy', providers: [] } })
    if (path === '/operations/jobs') return route.fulfill({ json: { worker: { status: 'healthy' }, jobs: [] } })
    if (path === '/backoffice/workspace') {
      return route.fulfill({
        json: {
          workspace_id: 'e2e',
          work_items: [item],
          pending_approvals: [],
          documents: [document],
          metrics: { work_items: 1, pending_approvals: 0, drafts: 0, policy_decisions: 0 },
        },
      })
    }
    if (path === '/invoices' && method === 'GET') {
      const needsCorrection = state.correctionRequested && !state.correctionSubmitted
      return route.fulfill({
        json: {
          items: [{
            ...document,
            vendor_name: extraction.data.vendor_name,
            total: extraction.data.total,
            currency: extraction.data.currency,
            business_status: state.approved ? 'approved' : needsCorrection ? 'needs_correction' : 'needs_review',
            current_owner: needsCorrection ? 'Uploader' : 'Reviewer',
            current_stage: needsCorrection ? 'correction_requested' : state.approved ? 'completed' : 'waiting_approval',
            work_item_id: 'item-1',
          }],
          page: 1,
          page_size: 100,
          total: 1,
          total_pages: 1,
        },
      })
    }
    if (path === '/backoffice/work-items/item-1') return route.fulfill({ json: { work_item: itemDetail } })
    if (path === '/documents/doc-1' && method === 'GET') {
      return route.fulfill({
        json: {
          document,
          extraction,
          correction_summary: correctionSummary(state),
          audit_events: state.approved
            ? [{ id: 'event-1', event_type: 'document_approved', actor: 'e2e-reviewer', new_status: 'approved', created_at: now }]
            : [],
        },
      })
    }
    if (path === '/documents/doc-1/workflow' && method === 'GET') {
      const needsCorrection = state.correctionRequested && !state.correctionSubmitted
      return route.fulfill({
        json: {
          document,
          extraction,
          correction_summary: correctionSummary(state),
          work_item: itemDetail,
          current_stage: needsCorrection ? 'correction_requested' : state.approved ? 'completed' : 'waiting_approval',
          current_owner: needsCorrection ? 'Uploader' : 'Reviewer',
          waiting_for: needsCorrection ? 'Uploader correction' : state.approved ? null : 'Reviewer decision',
          next_action: needsCorrection ? 'Correct the invoice and send it back' : state.approved ? 'No action needed' : 'Review invoice',
          attention_reason: needsCorrection ? 'Use the full legal vendor name.' : null,
          activity: [],
        },
      })
    }
    if (path === '/documents/doc-1/content') {
      return route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\n%%EOF' })
    }
    if (path === '/documents/doc-1/request-correction' && method === 'POST') {
      state.correctionRequested = true
      calls.push({ method, path, body: request.postDataJSON() })
      return route.fulfill({ json: { status: 'correction_requested' } })
    }
    if (path === '/invoices/doc-1/draft' && method === 'POST') {
      state.correctionSubmitted = true
      calls.push({ method, path, body: request.postDataJSON() })
      return route.fulfill({ json: { correction_recorded: true } })
    }
    if (path === '/review/doc-1/approve' && method === 'POST') {
      state.approved = true
      calls.push({ method, path, body: {} })
      return route.fulfill({ json: { review_task: { status: 'approved', reviewed_by: 'e2e-reviewer', reviewed_at: now } } })
    }

    return route.continue()
  })
}

async function navigatePrimary(page: Page, name: 'Approvals' | 'My Invoices') {
  const openNavigation = page.getByRole('button', { name: 'Open navigation' })
  if (await openNavigation.isVisible()) await openNavigation.click()
  await page.getByRole('button', { name }).click()
}

async function openReviewerInvoice(page: Page) {
  await navigatePrimary(page, 'Approvals')
  await page.getByRole('button', { name: 'Review invoice' }).click()
  await expect(page.getByText('INVOICE DATA')).toBeVisible()
}

test('reviewer requests a correction from the invoice decision screen', async ({ page }) => {
  const state: FlowState = { correctionRequested: false, correctionSubmitted: false, approved: false }
  const calls: RecordedCall[] = []
  await mockBusinessFlow(page, state, calls, 'administrator')
  await page.goto('/')
  await openReviewerInvoice(page)

  await page.getByPlaceholder('Example: Total and vendor match the PDF.').fill('Use the full legal vendor name.')
  await page.getByRole('button', { name: 'Request correction' }).click()

  await expect.poll(() => calls.some((call) => call.path === '/documents/doc-1/request-correction')).toBe(true)
  expect(calls.find((call) => call.path === '/documents/doc-1/request-correction')?.body).toEqual({ reason: 'Use the full legal vendor name.' })
})

test('uploader corrects invoice data and sends it back to the reviewer', async ({ page }) => {
  const state: FlowState = { correctionRequested: true, correctionSubmitted: false, approved: false }
  const calls: RecordedCall[] = []
  await mockBusinessFlow(page, state, calls, 'intake')
  await page.goto('/')
  await navigatePrimary(page, 'My Invoices')
  await page.getByRole('button', { name: 'View status' }).click()
  await page.getByRole('button', { name: 'Fix invoice' }).click()

  const vendor = page.getByRole('textbox', { name: 'Vendor' })
  await vendor.fill('Acme Logistics Ltd')
  const reason = page.getByRole('textbox', { name: 'Reason for the change' })
  await reason.fill('Used the legal vendor name.')
  await page.getByRole('button', { name: 'Send correction' }).click()

  await expect(page.getByText('Waiting approval')).toBeVisible()
  const draft = calls.find((call) => call.path === '/invoices/doc-1/draft')
  expect(draft?.body.vendor_name).toBe('Acme Logistics Ltd')
  expect(draft?.body.correction_reason).toBe('Used the legal vendor name.')
})

test('reviewer sees the correction summary before approval', async ({ page }) => {
  const state: FlowState = { correctionRequested: true, correctionSubmitted: true, approved: false }
  const calls: RecordedCall[] = []
  await mockBusinessFlow(page, state, calls, 'administrator')
  await page.goto('/')
  await openReviewerInvoice(page)

  await expect(page.getByText('1 field corrected by e2e-uploader')).toBeVisible()
  await expect(page.getByText(/Vendor\. Used the legal vendor name\./)).toBeVisible()
  await page.getByRole('button', { name: 'Approve', exact: true }).click()

  await expect.poll(() => calls.some((call) => call.path === '/review/doc-1/approve')).toBe(true)
  await expect(page.getByText('Decision recorded')).toBeVisible()
})
