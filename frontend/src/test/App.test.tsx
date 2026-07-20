import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { InvoiceItem, InvoiceListResponse } from '../features/invoices/types'
import type { ReviewWorklist } from '../features/review/types'
import type { ExportBatch, ExportInvoiceItem, ExportWorkspaceResponse } from '../features/exports/types'
import type { EvaluationDashboard } from '../features/evaluation/types'
import { queryClient } from '../queryClient'

vi.mock('../components/PdfPreview', () => ({
  PdfPreview: ({ filename }: { filename: string }) => <div aria-label="PDF preview">{filename}</div>,
}))

const now = '2026-07-20T09:41:00+00:00'
const workspace = { workspace_id: 'default', work_items: [], pending_approvals: [], documents: [], metrics: {} }
const emptyInvoices: InvoiceListResponse = {
  items: [], page: 1, page_size: 10, total: 0, total_pages: 1,
  summary: { all: 0, waiting_review: 0, needs_correction: 0, approved: 0, exported: 0 },
  insights: { flagged: 0, duplicates_suspected: 0, tax_amount_issues: 0 },
}
const invoice: InvoiceItem = {
  id: 'doc-1', original_filename: 'acme.pdf', submitted_by: 'uploader-1', status: 'needs_review', business_status: 'needs_review', current_stage: 'waiting_approval', current_owner: 'James Smith',
  vendor_name: 'Acme Logistics', invoice_number: 'INV-001', invoice_date: '2026-07-18', due_date: '2026-08-18', total: '1250.00', currency: 'USD', created_at: now, updated_at: now,
  validation_issue_count: 1, validation_error_count: 0, validation_codes: ['po_missing'], has_validation_errors: false, export_state: 'not_eligible', work_item_id: 'item-1',
}

function json(payload: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } }))
}

function installApi(session: Record<string, unknown>, invoiceResponse: InvoiceListResponse = emptyInvoices) {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const path = String(input)
    if (path === '/auth/session') return json(session)
    if (path === '/backoffice/workspace') return json(workspace)
    if (path.startsWith('/invoices?')) return json(invoiceResponse)
    if (path === '/documents/doc-1') return json({ document: invoice, extraction: { data: {}, validation: [{ field_name: 'po_number', severity: 'warning', code: 'po_missing', message: 'PO number was not found.' }], confidence: [] }, audit_events: [] })
    return json({ detail: `Unexpected request: ${path}` }, 404)
  }))
}

beforeEach(() => {
  queryClient.clear()
  window.history.replaceState({}, '', '/')
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

describe('product routes and role boundaries', () => {
  it('keeps an uploader inside the invoice library', async () => {
    installApi({ authenticated: true, actor: 'Upload User', user_id: 'uploader-1', workspace_id: 'default', role: 'uploader', is_admin: false })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload invoice/i })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: /primary/i })
    expect(within(navigation).getByRole('link', { name: 'Invoices' })).toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Overview' })).not.toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Review Queue' })).not.toBeInTheDocument()
  })

  it('shows reviewer work but hides administrator controls', async () => {
    installApi({ authenticated: true, actor: 'Reviewer', user_id: 'reviewer-1', workspace_id: 'default', role: 'reviewer', is_admin: false })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: /primary/i })
    expect(within(navigation).getByRole('link', { name: 'Review Queue' })).toBeInTheDocument()
    expect(within(navigation).getByRole('link', { name: 'Exceptions' })).toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Exports' })).not.toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'System' })).not.toBeInTheDocument()
  })

  it('guards a direct administrator route for an uploader', async () => {
    window.history.replaceState({}, '', '/system')
    installApi({ authenticated: true, actor: 'Upload User', user_id: 'uploader-1', workspace_id: 'default', role: 'uploader', is_admin: false })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/invoices')
  })
})

describe('invoice library', () => {
  it('renders server summaries and opens a read-only inspector', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/invoices')
    installApi(
      { authenticated: true, actor: 'Administrator', user_id: 'admin', workspace_id: 'default', role: 'administrator', is_admin: true },
      { ...emptyInvoices, items: [invoice], total: 1, summary: { ...emptyInvoices.summary, all: 1, waiting_review: 1 }, insights: { ...emptyInvoices.insights, flagged: 1 } },
    )
    render(<App />)
    expect(await screen.findByText('INV-001')).toBeInTheDocument()
    expect(screen.getByText('Invoices flagged').previousSibling).toHaveTextContent('1')
    await user.click(await screen.findByRole('button', { name: 'INV-001' }))
    const inspector = await screen.findByRole('region', { name: /invoice inspector/i })
    expect(within(inspector).getByText('Acme Logistics')).toBeInTheDocument()
    expect(within(inspector).getByText('PO number was not found.')).toBeInTheDocument()
    expect(within(inspector).queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(window.location.search).toContain('invoice=doc-1')
  })

  it('shows a sanitized session verification failure', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => String(input) === '/auth/session' ? json({ detail: 'stack trace' }, 500) : json({}, 404)))
    render(<App />)
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Unable to verify the secure session.')).toBeInTheDocument()
    expect(screen.queryByText('stack trace')).not.toBeInTheDocument()
  })
})

describe('review queue', () => {
  it('keeps decision actions in the dedicated review workspace', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review-queue')
    const worklist: ReviewWorklist = {
      items: [{
        id: 'doc-1', original_filename: 'acme.pdf', invoice_number: 'INV-001', vendor_name: 'Acme Logistics', total: '1250.00', currency: 'USD', invoice_date: '2026-07-18', due_date: '2026-08-18', owner: 'Reviewer', risk: 'high', confidence: .92, finding: 'PO number was not found.', blocker_count: 1, issue_count: 1, can_approve: false, recommended_action: 'request_correction', age_seconds: 900, created_at: now, updated_at: now,
      }],
      page: 1, page_size: 10, total: 1, total_pages: 1,
      summary: { in_queue: 1, high_risk: 1, invoice_due_today: 0, average_review_seconds: null },
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'Reviewer', user_id: 'reviewer', workspace_id: 'default', role: 'reviewer', is_admin: false })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/review/worklist?')) return json(worklist)
      if (path === '/documents/doc-1') return json({ document: invoice, extraction: { data: { vendor_name: 'Acme Logistics', invoice_number: 'INV-001', total: '1250.00', currency: 'USD' }, validation: [{ field_name: 'po_number', severity: 'error', code: 'po_missing', message: 'PO number was not found.' }], confidence: [] }, audit_events: [] })
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Review Queue' })).toBeInTheDocument()
    expect(screen.getByText('Not measured')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'INV-001' }))
    const inspector = await screen.findByRole('region', { name: /selected invoice review summary/i })
    expect(within(inspector).getByText('Request a correction because validation blockers remain.')).toBeInTheDocument()
    expect(within(inspector).getByRole('link', { name: /review invoice/i })).toHaveAttribute('href', '/review/doc-1')
    expect(within(inspector).queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
  })
})

describe('review workspace', () => {
  it('keeps blocker decisions explicit and requires a correction note', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review/doc-1')
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'Reviewer', user_id: 'reviewer', workspace_id: 'default', role: 'reviewer', is_admin: false })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path === '/documents/doc-1') return json({
        document: invoice,
        extraction: {
          data: { vendor_name: 'Acme Logistics', invoice_number: 'INV-001', invoice_date: '2026-07-18', due_date: '2026-08-18', subtotal: '1200.00', tax: '50.00', total: '1250.00', currency: 'USD', line_items: [] },
          validation: [{ field_name: 'po_number', severity: 'error', code: 'po_missing', message: 'PO number was not found.' }],
          confidence: [{ field_name: 'invoice_number', score: .92 }],
        },
        audit_events: [],
      })
      if (path === '/documents/doc-1/workflow') return json({ current_stage: 'waiting_approval', current_owner: 'Reviewer', waiting_for: 'reviewer', next_action: 'review', attention_reason: null, work_item: { assignee: 'Reviewer' } })
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Review invoice' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Invoice preview' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    const correction = screen.getByRole('button', { name: 'Request correction' })
    expect(correction).toBeDisabled()
    await user.type(screen.getByPlaceholderText('Explain the decision for the audit trail...'), 'Please provide the missing PO number.')
    expect(correction).toBeEnabled()
    await user.click(correction)
    const dialog = await screen.findByRole('dialog', { name: 'Request correction?' })
    expect(within(dialog).getByText('Please provide the missing PO number.')).toBeInTheDocument()
  })
})

describe('exceptions workspace', () => {
  it('keeps issue triage grounded and records assignment through the API', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/exceptions')
    const exception = {
      id: 'exception-1', document_id: 'doc-1', work_item_id: null, original_filename: 'acme.pdf', invoice_number: 'INV-001', vendor_name: 'Acme Logistics', total: '1250.00', currency: 'USD', issue: 'Missing invoice number', category: 'vendor_invoice', risk: 'high', blocks_approval: true, owner: null, detected_at: now, age_seconds: 900,
    }
    const detail = {
      ...exception, message: 'Invoice number is required.', code: 'missing_critical_field', field_name: 'invoice_number', field_value: null, required_action: 'Add or request a valid invoice number, then save the invoice so validation can run again.', related_checks: [{ label: 'Invoice extracted', status: 'passed' }, { label: 'Invoice number present', status: 'blocked' }],
    }
    const list = {
      items: [exception], page: 1, page_size: 10, total: 1, total_pages: 1,
      summary: { open_exceptions: 1, high_risk: 1, warning_issues: 0, invoices_affected: 1, categories: { vendor_invoice: 1 }, top_issues: [{ label: 'Missing invoice number', category: 'vendor_invoice', count: 1 }] },
      assignee_options: ['Reviewer'], capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'Reviewer', user_id: 'reviewer', workspace_id: 'default', role: 'reviewer', is_admin: false })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/exceptions?')) return json(list)
      if (path === '/exceptions/exception-1' && !init?.method) return json({ exception: detail })
      if (path === '/exceptions/exception-1/assignment' && init?.method === 'PATCH') return json({ exception: { ...detail, owner: 'Senior Reviewer', work_item_id: 'item-1' }, assignment: { work_item_id: 'item-1', assignee: 'Senior Reviewer', recorded_by: 'Reviewer', recorded_at: now } })
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Exceptions' })).toBeInTheDocument()
    expect((await screen.findByText('Open exceptions')).previousSibling).toHaveTextContent('1')
    await user.click(screen.getByRole('button', { name: 'INV-001' }))
    const inspector = await screen.findByRole('region', { name: 'Exception details' })
    expect(within(inspector).getByText('Approval is blocked until this issue is resolved.')).toBeInTheDocument()
    expect(within(inspector).getByRole('link', { name: /open invoice/i })).toHaveAttribute('href', '/review/doc-1?from=exceptions&exception=exception-1')
    await user.click(within(inspector).getByRole('button', { name: 'Assign' }))
    const dialog = await screen.findByRole('dialog', { name: 'Assign exception' })
    const input = within(dialog).getByLabelText('Owner')
    await user.clear(input)
    await user.type(input, 'Senior Reviewer')
    await user.click(within(dialog).getByRole('button', { name: 'Save assignment' }))
    expect(await screen.findByText('Assigned to Senior Reviewer')).toBeInTheDocument()
  })
})

describe('exports workspace', () => {
  it('builds a server-validated batch and exposes only configured capabilities', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/exports')
    const exportInvoice: ExportInvoiceItem = {
      id: 'doc-1', invoice_label: 'INV-001', filename: 'acme.pdf', vendor_name: 'Acme Logistics', approved_by: 'Reviewer', approved_at: now, total: '1250.00', currency: 'USD', status: 'ready', issue: null, batch_id: null, updated_at: now,
    }
    const base: ExportWorkspaceResponse = {
      capabilities: { destinations: [{ id: 'csv_download', label: 'CSV download', formats: ['csv'], mode: 'file_download' }], scheduling: false, drafts: true, retry: true, configured_provider: 'csv_download', destination_available: true },
      summary: { ready: { count: 1, amount: '1250.00', currency: 'USD' }, in_batch: { count: 0, amount: '0', currency: null }, exported: { count: 0, amount: '0', currency: null }, blocked: { count: 0, amount: '0', currency: null } },
      items: [exportInvoice], page: 1, page_size: 10, total: 1, total_pages: 1,
      filters: { vendors: ['Acme Logistics'], currencies: ['USD'], approvers: ['Reviewer'] }, batch: null, recent_runs: [],
    }
    const batch: ExportBatch = {
      id: 'batch-1', name: null, status: 'ready', destination: 'csv_download', destination_label: 'CSV download', format: 'csv', created_by: 'Administrator', invoice_count: 1, total_amount: '1250.00', currency: 'USD', invoices: [{ ...exportInvoice, status: 'in_batch', batch_id: 'batch-1' }], eligibility: [
        { code: 'all_approved', label: 'All invoices approved', state: 'passed', detail: 'Verified from current records.' },
        { code: 'destination_available', label: 'Destination is available', state: 'passed', detail: 'Verified from current records.' },
      ], last_run_id: null, created_at: now, updated_at: now,
    }
    let batchCreated = false
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'Administrator', user_id: 'admin', workspace_id: 'default', role: 'administrator', is_admin: true })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/exports/workspace?')) return json(batchCreated ? { ...base, items: [{ ...exportInvoice, status: 'in_batch', batch_id: 'batch-1' }], summary: { ...base.summary, ready: { count: 0, amount: '0', currency: null }, in_batch: { count: 1, amount: '1250.00', currency: 'USD' } }, batch } : base)
      if (path === '/exports/batches' && init?.method === 'POST') { batchCreated = true; return json({ batch, accepted: ['doc-1'], rejected: [] }) }
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Exports' })).toBeInTheDocument()
    expect(screen.queryByText('NetSuite')).not.toBeInTheDocument()
    expect(screen.queryByText(/schedule export/i)).not.toBeInTheDocument()
    await user.click(await screen.findByRole('checkbox', { name: 'Select INV-001' }))
    await user.click(screen.getByRole('button', { name: /add to export/i }))
    expect(await screen.findByText('1 invoices added to export batch.')).toBeInTheDocument()
    expect(await screen.findByText('CSV download')).toBeInTheDocument()
    expect(await screen.findByText('All invoices approved')).toBeInTheDocument()
    const panel = screen.getByRole('complementary', { name: 'Export batch' })
    expect(within(panel).getByRole('button', { name: 'Create export' })).toBeEnabled()
  })
})

describe('evaluation workspace', () => {
  it('keeps synthetic claims bounded and makes comparisons inspectable', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/evaluation')
    const run = {
      id: 'run-current', label: 'External holdout', dataset_id: 'invoice_holdout_v2', dataset_version: '2.0', dataset_class: 'synthetic', split: 'external_holdout', provider: 'mistral + openai', source: 'public_evidence', source_document: 'docs/evidence/run.json', observed_at: now,
      documents: 10, fields_matched: 79, fields_total: 80, field_match: .9875, validation_match: 1, document_exact_match: .9, approval_blocker_accuracy: 1, provider_errors: 0, duration_seconds: 65.8, duration_kind: 'wall_clock' as const, provider_calls: 20, estimated_cost_usd: .0636, cost_status: 'estimated', cost_claim: 'Estimated from recorded usage.', passed: true, verdict_available: true, by_field: { invoice_number: 1, tax: .9 }, failure_taxonomy: { hallucinated_value: 1 }, limitations: ['Synthetic documents only.', 'No production accuracy claim.'], is_current: true,
    }
    const dashboard: EvaluationDashboard = {
      gates: { field_match: .95, validation_match: .95, regression_tolerance_pp: .5 },
      preflight: { dataset_id: 'invoice_scenarios_v1', dataset_version: '1.0', dataset_label: 'Invoice scenarios', available_documents: 20, documents: 3, limited: true, provider_calls_estimate: 6, estimated_cost_usd: null, cost_note: 'Cost is calculated from observed provider usage after completion.', runnable: true, provider: 'mistral + openai' },
      runs: [
        { id: 'run-current', label: 'External holdout', dataset_id: 'invoice_holdout_v2', split: 'external_holdout', observed_at: now, passed: true, verdict_available: true, current: true },
        { id: 'run-previous', label: 'Comparable baseline', dataset_id: 'invoice_holdout_v2', split: 'external_holdout', observed_at: '2026-06-26T09:41:00+00:00', passed: true, verdict_available: true, current: false },
      ],
      selected_run: run,
      trend: [
        { id: 'run-previous', observed_at: '2026-06-26T09:41:00+00:00', field_match: .98, validation_match: .98, documents: 10, provider_errors: 0, estimated_cost_usd: .06, selected: false },
        { id: 'run-current', observed_at: now, field_match: .9875, validation_match: 1, documents: 10, provider_errors: 0, estimated_cost_usd: .0636, selected: true },
      ],
      regression: { comparison_run_id: 'run-previous', comparison_observed_at: '2026-06-26T09:41:00+00:00', tolerance_pp: .5, comparable_fields: 2, improved: 1, stable: 0, regressed: 1, new_fields: 0, excluded_fields: 0, new_failures: 0 },
      fields: [
        { field: 'invoice_number', label: 'Invoice number', current: 1, previous: .98, delta_pp: 2, status: 'improved', current_matches: 10, current_denominator: 10, previous_matches: 10, previous_denominator: 10 },
        { field: 'tax', label: 'Tax', current: .9, previous: .92, delta_pp: -2, status: 'regressed', current_matches: 9, current_denominator: 10, previous_matches: 9, previous_denominator: 10 },
      ],
      scenario_coverage: { dataset_id: 'invoice_scenarios_v1', dataset_version: '1.0', claim_boundary: 'Coverage is case inventory, not accuracy.', included_in_selected_run: false, groups: [{ id: 'missing', label: 'Missing fields', current: 4, target: 5, coverage: .8, remaining: 1, case_ids: ['missing_vendor', 'missing_date'] }] },
      attempts: [],
    }
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'Administrator', user_id: 'admin', workspace_id: 'default', role: 'administrator', is_admin: true })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/evaluation/dashboard?')) return json(dashboard)
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }))
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Evaluation' })).toBeInTheDocument()
    expect(screen.getByText('Synthetic evidence')).toBeInTheDocument()
    expect(screen.getByText(/directional, not production accuracy/i)).toBeInTheDocument()
    expect((await screen.findAllByText('Estimated cost'))[0].closest('.ops-panel')).toHaveTextContent('$0.0636')

    await user.click(screen.getByText('Regressed').closest('button')!)
    expect(screen.getByText('Tax')).toBeInTheDocument()
    expect(screen.queryByText('Invoice number')).not.toBeInTheDocument()
    await user.click(screen.getByText('Tax').closest('tr')!)
    expect(await screen.findByRole('dialog', { name: 'Tax' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close details' }))

    await user.click(screen.getByRole('button', { name: /missing fields/i }))
    expect(await screen.findByRole('dialog', { name: 'Missing fields' })).toHaveTextContent('Coverage is case inventory, not accuracy.')
    await user.click(screen.getByRole('button', { name: 'Close details' }))

    await user.click(screen.getByRole('button', { name: 'Run evaluation' }))
    const dialog = await screen.findByRole('dialog', { name: 'Run evaluation?' })
    expect(within(dialog).getByText('3 of 20 (safety cap)')).toBeInTheDocument()
    expect(within(dialog).getByText('Calculated after completion')).toBeInTheDocument()
    expect(within(dialog).getByText('6')).toBeInTheDocument()
  })
})
