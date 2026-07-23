import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { InvoiceItem, InvoiceListResponse } from '../features/invoices/types'
import type { ReviewWorklist } from '../features/review/types'
import type { ExceptionListResponse } from '../features/exceptions/types'
import type {
  ExportBatch,
  ExportInvoiceItem,
  ExportWorkspaceResponse,
} from '../features/exports/types'
import type { EvaluationDashboard } from '../features/evaluation/types'
import type { SystemDashboard } from '../features/system/types'
import { queryClient } from '../queryClient'

vi.mock('../components/PdfPreview', () => ({
  PdfPreview: ({ filename }: { filename: string }) => (
    <div aria-label="PDF preview">{filename}</div>
  ),
}))

const now = '2026-07-20T09:41:00+00:00'
const workspace = {
  workspace_id: 'default',
  work_items: [],
  pending_approvals: [],
  documents: [],
  metrics: {},
}
const emptyInvoices: InvoiceListResponse = {
  items: [],
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 1,
  summary: { all: 0, waiting_review: 0, needs_correction: 0, approved: 0, exported: 0 },
  insights: { flagged: 0, duplicates_suspected: 0, tax_amount_issues: 0 },
}
const emptyWorklist: ReviewWorklist = {
  items: [],
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 1,
  summary: { in_queue: 0, high_risk: 0, invoice_due_today: 0, average_review_seconds: null },
}
const emptyExceptions: ExceptionListResponse = {
  items: [],
  page: 1,
  page_size: 12,
  total: 0,
  total_pages: 1,
  summary: {
    open_exceptions: 0,
    high_risk: 0,
    warning_issues: 0,
    invoices_affected: 0,
    categories: {},
    top_issues: [],
  },
  assignee_options: [],
  capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
}
const invoice: InvoiceItem = {
  id: 'doc-1',
  original_filename: 'acme.pdf',
  submitted_by: 'uploader-1',
  status: 'needs_review',
  business_status: 'needs_review',
  current_stage: 'waiting_approval',
  current_owner: 'James Smith',
  vendor_name: 'Acme Logistics',
  invoice_number: 'INV-001',
  invoice_date: '2026-07-18',
  due_date: '2026-08-18',
  total: '1250.00',
  currency: 'USD',
  created_at: now,
  updated_at: now,
  validation_issue_count: 1,
  validation_error_count: 0,
  validation_codes: ['po_missing'],
  has_validation_errors: false,
  export_state: 'not_eligible',
  work_item_id: 'item-1',
  correction_reason: null,
}
function json(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function installApi(
  session: Record<string, unknown>,
  invoiceResponse: InvoiceListResponse = emptyInvoices,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json(session)
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/review/worklist?')) return json(emptyWorklist)
      if (path.startsWith('/exceptions?')) return json(emptyExceptions)
      if (path.startsWith('/invoices?')) return json(invoiceResponse)
      if (path === '/documents/doc-1')
        return json({
          document: invoice,
          extraction: {
            data: {},
            validation: [
              {
                field_name: 'po_number',
                severity: 'warning',
                code: 'po_missing',
                message: 'PO number was not found.',
              },
            ],
            confidence: [],
          },
          audit_events: [],
        })
      return json({ detail: `Unexpected request: ${path}` }, 404)
    }),
  )
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
    installApi({
      authenticated: true,
      actor: 'Upload User',
      user_id: 'uploader-1',
      workspace_id: 'default',
      role: 'uploader',
      is_admin: false,
    })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Invoices' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload invoice/i })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: /primary/i })
    expect(within(navigation).getByRole('link', { name: 'Invoices' })).toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Inbox' })).not.toBeInTheDocument()
  })

  it('shows reviewer work but hides administrator controls', async () => {
    installApi({
      authenticated: true,
      actor: 'Reviewer',
      user_id: 'reviewer-1',
      workspace_id: 'default',
      role: 'reviewer',
      is_admin: false,
    })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByText('No invoices need a decision')).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: /primary/i })
    expect(within(navigation).getByRole('link', { name: 'Inbox' })).toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Exports' })).not.toBeInTheDocument()
    expect(within(navigation).queryByRole('link', { name: 'Operations' })).not.toBeInTheDocument()
  })

  it('guards a direct administrator route for an uploader', async () => {
    window.history.replaceState({}, '', '/system')
    installApi({
      authenticated: true,
      actor: 'Upload User',
      user_id: 'uploader-1',
      workspace_id: 'default',
      role: 'uploader',
      is_admin: false,
    })
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
      {
        authenticated: true,
        actor: 'Administrator',
        user_id: 'admin',
        workspace_id: 'default',
        role: 'administrator',
        is_admin: true,
      },
      {
        ...emptyInvoices,
        items: [invoice],
        total: 1,
        summary: { ...emptyInvoices.summary, all: 1, waiting_review: 1 },
        insights: { ...emptyInvoices.insights, flagged: 1 },
      },
    )
    render(<App />)
    expect(await screen.findByText('INV-001')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /All\s*1/ })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'INV-001' }))
    const inspector = await screen.findByRole('region', { name: /invoice inspector/i })
    expect(within(inspector).getByText('Acme Logistics')).toBeInTheDocument()
    expect(within(inspector).getByText('PO number was not found.')).toBeInTheDocument()
    expect(within(inspector).queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(window.location.search).toContain('invoice=doc-1')
  })

  it('lets the uploader answer a reviewer correction request', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/invoices?invoice=doc-1')
    const correctionInvoice: InvoiceItem = {
      ...invoice,
      business_status: 'needs_correction',
      current_stage: 'correction_requested',
      current_owner: 'Uploader',
      correction_reason: 'Use the full legal vendor name shown on the PDF.',
    }
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/auth/session')
        return json({
          authenticated: true,
          actor: 'Upload User',
          user_id: 'uploader-1',
          workspace_id: 'default',
          role: 'uploader',
          is_admin: false,
        })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path.startsWith('/invoices?'))
        return json({
          ...emptyInvoices,
          items: [correctionInvoice],
          total: 1,
          summary: { ...emptyInvoices.summary, all: 1, needs_correction: 1 },
        })
      if (path === '/documents/doc-1')
        return json({
          document: correctionInvoice,
          extraction: {
            data: {
              vendor_name: 'Acme Logistics',
              invoice_number: 'INV-001',
              invoice_date: '2026-07-18',
              due_date: '2026-08-18',
              subtotal: '1200.00',
              tax: '50.00',
              total: '1250.00',
              currency: 'USD',
              line_items: [],
            },
            validation: [],
            confidence: [],
          },
          audit_events: [],
        })
      if (path === '/invoices/doc-1/draft' && init?.method === 'POST')
        return json({ correction_recorded: true })
      return json({ detail: `Unexpected request: ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    expect(
      await screen.findByText('Use the full legal vendor name shown on the PDF.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Correct invoice data' }))
    const dialog = await screen.findByRole('dialog', { name: 'Correct invoice data' })
    await user.clear(within(dialog).getByRole('textbox', { name: 'Vendor' }))
    await user.type(within(dialog).getByRole('textbox', { name: 'Vendor' }), 'Acme Logistics Ltd')
    await user.type(
      within(dialog).getByRole('textbox', { name: 'What did you change?' }),
      'Matched the legal name on the PDF.',
    )
    await user.click(within(dialog).getByRole('button', { name: 'Send to reviewer' }))

    expect(await screen.findByText('Correction sent back to the reviewer.')).toBeInTheDocument()
    const request = fetchMock.mock.calls.find(
      ([path, init]) => path === '/invoices/doc-1/draft' && init?.method === 'POST',
    )
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({
      vendor_name: 'Acme Logistics Ltd',
      correction_reason: 'Matched the legal name on the PDF.',
    })
  })

  it('shows a sanitized session verification failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) =>
        String(input) === '/auth/session' ? json({ detail: 'stack trace' }, 500) : json({}, 404),
      ),
    )
    render(<App />)
    expect(await screen.findByText('Unable to verify the secure session.')).toBeInTheDocument()
    expect(screen.queryByText('stack trace')).not.toBeInTheDocument()
  })
})

describe('review queue', () => {
  it('keeps decision actions in the dedicated review workspace', async () => {
    window.history.replaceState({}, '', '/review-queue')
    const worklist: ReviewWorklist = {
      items: [
        {
          id: 'doc-1',
          original_filename: 'acme.pdf',
          invoice_number: 'INV-001',
          vendor_name: 'Acme Logistics',
          total: '1250.00',
          currency: 'USD',
          invoice_date: '2026-07-18',
          due_date: '2026-08-18',
          owner: 'Reviewer',
          risk: 'high',
          confidence: 0.92,
          finding: 'PO number was not found.',
          blocker_count: 1,
          issue_count: 1,
          can_approve: false,
          recommended_action: 'request_correction',
          age_seconds: 900,
          created_at: now,
          updated_at: now,
        },
      ],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
      summary: { in_queue: 1, high_risk: 1, invoice_due_today: 0, average_review_seconds: null },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Reviewer',
            user_id: 'reviewer',
            workspace_id: 'default',
            role: 'reviewer',
            is_admin: false,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path.startsWith('/review/worklist?')) return json(worklist)
        if (path === '/documents/doc-1')
          return json({
            document: invoice,
            extraction: {
              data: {
                vendor_name: 'Acme Logistics',
                invoice_number: 'INV-001',
                total: '1250.00',
                currency: 'USD',
              },
              validation: [
                {
                  field_name: 'po_number',
                  severity: 'error',
                  code: 'po_missing',
                  message: 'PO number was not found.',
                },
              ],
              confidence: [],
            },
            audit_events: [],
          })
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByText('PO number was not found.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^review/i })).toHaveAttribute(
      'href',
      '/review/doc-1?from=inbox',
    )
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
  })
})

describe('review workspace', () => {
  it('keeps blocker decisions explicit and requires a correction note', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/review/doc-1')
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Reviewer',
            user_id: 'reviewer',
            workspace_id: 'default',
            role: 'reviewer',
            is_admin: false,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path === '/documents/doc-1')
          return json({
            document: invoice,
            extraction: {
              data: {
                vendor_name: 'Acme Logistics',
                invoice_number: 'INV-001',
                invoice_date: '2026-07-18',
                due_date: '2026-08-18',
                subtotal: '1200.00',
                tax: '50.00',
                total: '1250.00',
                currency: 'USD',
                line_items: [],
              },
              validation: [
                {
                  field_name: 'po_number',
                  severity: 'error',
                  code: 'po_missing',
                  message: 'PO number was not found.',
                },
              ],
              confidence: [{ field_name: 'invoice_number', score: 0.92 }],
            },
            audit_events: [],
          })
        if (path === '/documents/doc-1/workflow')
          return json({
            current_stage: 'waiting_approval',
            current_owner: 'Reviewer',
            waiting_for: 'reviewer',
            next_action: 'review',
            attention_reason: null,
            work_item: { assignee: 'Reviewer' },
          })
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Review invoice' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Invoice preview' })).toBeInTheDocument()
    expect(screen.getByText('Approval blocked')).toBeInTheDocument()
    const trigger = screen.getByRole('button', { name: 'Open decision panel' })
    expect(screen.queryByRole('dialog', { name: 'Reviewer decision' })).not.toBeInTheDocument()
    await user.click(trigger)
    const panel = screen.getByRole('dialog', { name: 'Reviewer decision' })
    expect(within(panel).getByRole('button', { name: 'Close decision panel' })).toHaveFocus()
    expect(within(panel).getByRole('button', { name: 'Approve' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Reviewer decision' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    const reopenedPanel = screen.getByRole('dialog', { name: 'Reviewer decision' })
    const correction = within(reopenedPanel).getByRole('button', { name: 'Request correction' })
    expect(correction).toBeDisabled()
    await user.type(
      within(reopenedPanel).getByPlaceholderText('Explain the decision for the audit trail...'),
      'Please provide the missing PO number.',
    )
    expect(correction).toBeEnabled()
    await user.click(correction)
    const dialog = await screen.findByRole('dialog', { name: 'Request correction?' })
    expect(within(dialog).getByText('Please provide the missing PO number.')).toBeInTheDocument()
  })
})

describe('blocked inbox', () => {
  it('shows grounded blocker context and links to the review workspace', async () => {
    window.history.replaceState({}, '', '/inbox?state=blocked')
    const exception = {
      id: 'exception-1',
      document_id: 'doc-1',
      work_item_id: null,
      original_filename: 'acme.pdf',
      invoice_number: 'INV-001',
      vendor_name: 'Acme Logistics',
      total: '1250.00',
      currency: 'USD',
      issue: 'Missing invoice number',
      category: 'vendor_invoice',
      risk: 'high',
      blocks_approval: true,
      owner: null,
      detected_at: now,
      age_seconds: 900,
    }
    const list = {
      items: [exception],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
      summary: {
        open_exceptions: 1,
        high_risk: 1,
        warning_issues: 0,
        invoices_affected: 1,
        categories: { vendor_invoice: 1 },
        top_issues: [{ label: 'Missing invoice number', category: 'vendor_invoice', count: 1 }],
      },
      assignee_options: ['Reviewer'],
      capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Reviewer',
            user_id: 'reviewer',
            workspace_id: 'default',
            role: 'reviewer',
            is_admin: false,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path.startsWith('/review/worklist?')) return json(emptyWorklist)
        if (path.startsWith('/exceptions?')) return json(list)
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Inbox' })).toBeInTheDocument()
    expect(await screen.findByText('Missing invoice number')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Blocked\s*1/ })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('link', { name: /^resolve/i })).toHaveAttribute(
      'href',
      '/review/doc-1?from=inbox&state=blocked&exception=exception-1',
    )
  })
})

describe('exports workspace', () => {
  it('builds a server-validated batch and exposes only configured capabilities', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/exports')
    const exportInvoice: ExportInvoiceItem = {
      id: 'doc-1',
      invoice_label: 'INV-001',
      filename: 'acme.pdf',
      vendor_name: 'Acme Logistics',
      approved_by: 'Reviewer',
      approved_at: now,
      total: '1250.00',
      currency: 'USD',
      status: 'ready',
      issue: null,
      batch_id: null,
      updated_at: now,
    }
    const base: ExportWorkspaceResponse = {
      capabilities: {
        destinations: [
          { id: 'csv_download', label: 'CSV download', formats: ['csv'], mode: 'file_download' },
        ],
        scheduling: false,
        drafts: true,
        retry: true,
        configured_provider: 'csv_download',
        destination_available: true,
      },
      summary: {
        ready: { count: 1, amount: '1250.00', currency: 'USD' },
        in_batch: { count: 0, amount: '0', currency: null },
        exported: { count: 0, amount: '0', currency: null },
        blocked: { count: 0, amount: '0', currency: null },
      },
      items: [exportInvoice],
      page: 1,
      page_size: 10,
      total: 1,
      total_pages: 1,
      filters: { vendors: ['Acme Logistics'], currencies: ['USD'], approvers: ['Reviewer'] },
      batch: null,
      recent_runs: [],
    }
    const batch: ExportBatch = {
      id: 'batch-1',
      name: null,
      status: 'ready',
      destination: 'csv_download',
      destination_label: 'CSV download',
      format: 'csv',
      created_by: 'Administrator',
      invoice_count: 1,
      total_amount: '1250.00',
      currency: 'USD',
      invoices: [{ ...exportInvoice, status: 'in_batch', batch_id: 'batch-1' }],
      eligibility: [
        {
          code: 'all_approved',
          label: 'All invoices approved',
          state: 'passed',
          detail: 'Verified from current records.',
        },
        {
          code: 'destination_available',
          label: 'Destination is available',
          state: 'passed',
          detail: 'Verified from current records.',
        },
      ],
      last_run_id: null,
      created_at: now,
      updated_at: now,
    }
    let batchCreated = false
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Administrator',
            user_id: 'admin',
            workspace_id: 'default',
            role: 'administrator',
            is_admin: true,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path.startsWith('/exports/workspace?'))
          return json(
            batchCreated
              ? {
                  ...base,
                  items: [{ ...exportInvoice, status: 'in_batch', batch_id: 'batch-1' }],
                  summary: {
                    ...base.summary,
                    ready: { count: 0, amount: '0', currency: null },
                    in_batch: { count: 1, amount: '1250.00', currency: 'USD' },
                  },
                  batch,
                }
              : base,
          )
        if (path === '/exports/batches' && init?.method === 'POST') {
          batchCreated = true
          return json({ batch, accepted: ['doc-1'], rejected: [] })
        }
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
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
      id: 'run-current',
      label: 'External holdout',
      dataset_id: 'invoice_holdout_v2',
      dataset_version: '2.0',
      dataset_class: 'synthetic',
      split: 'external_holdout',
      provider: 'mistral + openai',
      source: 'public_evidence',
      source_document: 'docs/evidence/run.json',
      observed_at: now,
      documents: 10,
      fields_matched: 79,
      fields_total: 80,
      field_match: 0.9875,
      validation_match: 1,
      document_exact_match: 0.9,
      approval_blocker_accuracy: 1,
      provider_errors: 0,
      duration_seconds: 65.8,
      duration_kind: 'wall_clock' as const,
      provider_calls: 20,
      estimated_cost_usd: 0.0636,
      cost_status: 'estimated',
      cost_claim: 'Estimated from recorded usage.',
      passed: true,
      verdict_available: true,
      by_field: { invoice_number: 1, tax: 0.9 },
      failure_taxonomy: { hallucinated_value: 1 },
      limitations: ['Synthetic documents only.', 'No production accuracy claim.'],
      is_current: true,
    }
    const dashboard: EvaluationDashboard = {
      gates: { field_match: 0.95, validation_match: 0.95, regression_tolerance_pp: 0.5 },
      preflight: {
        dataset_id: 'invoice_scenarios_v1',
        dataset_version: '1.0',
        dataset_label: 'Invoice scenarios',
        available_documents: 20,
        documents: 3,
        limited: true,
        provider_calls_estimate: 6,
        estimated_cost_usd: null,
        cost_note: 'Cost is calculated from observed provider usage after completion.',
        runnable: true,
        provider: 'mistral + openai',
      },
      runs: [
        {
          id: 'run-current',
          label: 'External holdout',
          dataset_id: 'invoice_holdout_v2',
          split: 'external_holdout',
          observed_at: now,
          passed: true,
          verdict_available: true,
          current: true,
        },
        {
          id: 'run-previous',
          label: 'Comparable baseline',
          dataset_id: 'invoice_holdout_v2',
          split: 'external_holdout',
          observed_at: '2026-06-26T09:41:00+00:00',
          passed: true,
          verdict_available: true,
          current: false,
        },
      ],
      selected_run: run,
      trend: [
        {
          id: 'run-previous',
          observed_at: '2026-06-26T09:41:00+00:00',
          field_match: 0.98,
          validation_match: 0.98,
          documents: 10,
          provider_errors: 0,
          estimated_cost_usd: 0.06,
          selected: false,
        },
        {
          id: 'run-current',
          observed_at: now,
          field_match: 0.9875,
          validation_match: 1,
          documents: 10,
          provider_errors: 0,
          estimated_cost_usd: 0.0636,
          selected: true,
        },
      ],
      regression: {
        comparison_run_id: 'run-previous',
        comparison_observed_at: '2026-06-26T09:41:00+00:00',
        tolerance_pp: 0.5,
        comparable_fields: 2,
        improved: 1,
        stable: 0,
        regressed: 1,
        new_fields: 0,
        excluded_fields: 0,
        new_failures: 0,
      },
      fields: [
        {
          field: 'invoice_number',
          label: 'Invoice number',
          current: 1,
          previous: 0.98,
          delta_pp: 2,
          status: 'improved',
          current_matches: 10,
          current_denominator: 10,
          previous_matches: 10,
          previous_denominator: 10,
        },
        {
          field: 'tax',
          label: 'Tax',
          current: 0.9,
          previous: 0.92,
          delta_pp: -2,
          status: 'regressed',
          current_matches: 9,
          current_denominator: 10,
          previous_matches: 9,
          previous_denominator: 10,
        },
      ],
      scenario_coverage: {
        dataset_id: 'invoice_scenarios_v1',
        dataset_version: '1.0',
        claim_boundary: 'Coverage is case inventory, not accuracy.',
        included_in_selected_run: false,
        groups: [
          {
            id: 'missing',
            label: 'Missing fields',
            current: 4,
            target: 5,
            coverage: 0.8,
            remaining: 1,
            case_ids: ['missing_vendor', 'missing_date'],
          },
        ],
      },
      attempts: [],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Administrator',
            user_id: 'admin',
            workspace_id: 'default',
            role: 'administrator',
            is_admin: true,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path.startsWith('/evaluation/dashboard?')) return json(dashboard)
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Quality' })).toBeInTheDocument()
    expect(screen.getByText('Synthetic test set')).toBeInTheDocument()
    expect(screen.getByTitle(/do not represent production accuracy/i)).toBeInTheDocument()
    expect(
      (await screen.findAllByText('Estimated cost'))[0].closest('.ops-panel'),
    ).toHaveTextContent('$0.0636')
    expect(screen.queryByText('Quality trend over time')).not.toBeInTheDocument()

    expect(screen.getByText('Tax')).toBeInTheDocument()
    expect(screen.getByText('Invoice number')).toBeInTheDocument()
    await user.click(screen.getByText('Tax').closest('tr')!)
    expect(await screen.findByRole('dialog', { name: 'Tax' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Close details' }))

    await user.click(screen.getByRole('button', { name: /missing fields/i }))
    expect(await screen.findByRole('dialog', { name: 'Missing fields' })).toHaveTextContent(
      'Coverage is case inventory, not accuracy.',
    )
    await user.click(screen.getByRole('button', { name: 'Close details' }))

    await user.click(screen.getByRole('button', { name: 'Run evaluation' }))
    const dialog = await screen.findByRole('dialog', { name: 'Run evaluation?' })
    expect(within(dialog).getByText('3 of 20 (safety cap)')).toBeInTheDocument()
    expect(within(dialog).getByText('Calculated after completion')).toBeInTheDocument()
    expect(within(dialog).getByText('6')).toBeInTheDocument()
  })
})

describe('system workspace', () => {
  it('keeps operational evidence honest and navigates tabs without a page reload', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/system')
    const dashboard = systemDashboard()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session')
        return json({
          authenticated: true,
          actor: 'Administrator',
          user_id: 'admin',
          workspace_id: 'default',
          role: 'administrator',
          is_admin: true,
        })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path === '/system/dashboard') return json(dashboard)
      return json({ detail: `Unexpected request: ${path}` }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Operations' })).toBeInTheDocument()
    expect((await screen.findAllByText('Not enough history')).length).toBeGreaterThan(0)
    expect(screen.queryByText(/99\.\d+%/)).not.toBeInTheDocument()
    const readerRow = screen
      .getAllByText('Document reader')
      .map((item) => item.closest('tr'))
      .find(Boolean)!
    await user.click(within(readerRow).getByRole('button', { name: /view/i }))
    expect(await screen.findByRole('dialog', { name: 'Document reader' })).toHaveTextContent(
      'No observed provider run',
    )
    await user.click(screen.getByRole('button', { name: 'Close details' }))

    await user.click(screen.getByRole('tab', { name: 'Processing' }))
    expect(window.location.search).toContain('tab=processing')
    expect(await screen.findByRole('heading', { name: 'Processing activity' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /refresh status/i }))
    expect(await screen.findByText('Operations status refreshed.')).toBeInTheDocument()
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === '/system/dashboard').length,
    ).toBeGreaterThan(1)
  })

  it('offers retry only for a failed job accepted by the backend contract', async () => {
    const user = userEvent.setup()
    window.history.replaceState({}, '', '/system?tab=processing&filter=attention')
    const dashboard = systemDashboard()
    dashboard.kpis.needs_attention = 1
    dashboard.alerts = [
      {
        id: 'job:job-1',
        kind: 'job',
        target_id: 'job-1',
        severity: 'warning',
        title: 'Invoice processing needs attention',
        detail: 'acme.pdf: Invoice processing did not complete.',
      },
    ]
    dashboard.recent_jobs = [
      {
        id: 'job-1',
        document_id: 'doc-1',
        invoice: 'INV-001',
        filename: 'acme.pdf',
        stage: 'Processing failed',
        status: 'failed',
        started_at: now,
        finished_at: now,
        duration_ms: 1200,
        attempt_count: 1,
        retryable: true,
        failure_summary: 'Invoice processing did not complete.',
      },
    ]
    let retried = false
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path === '/auth/session')
          return json({
            authenticated: true,
            actor: 'Administrator',
            user_id: 'admin',
            workspace_id: 'default',
            role: 'administrator',
            is_admin: true,
          })
        if (path === '/backoffice/workspace') return json(workspace)
        if (path === '/system/dashboard') return json(dashboard)
        if (path === '/operations/jobs/job-1/retry' && init?.method === 'POST') {
          retried = true
          return json({ job: { id: 'job-2', status: 'queued' } })
        }
        return json({ detail: `Unexpected request: ${path}` }, 404)
      }),
    )
    render(<App />)

    await user.click(await screen.findByRole('button', { name: /retry/i }))
    expect(retried).toBe(true)
    expect(await screen.findByText(/retry accepted/i)).toBeInTheDocument()
  })
})

function systemDashboard(): SystemDashboard {
  return {
    observed_at: now,
    freshness: { state: 'current', label: 'Observed when this page was refreshed' },
    overall: {
      status: 'unknown',
      title: 'Operational status is partially unverified',
      detail: 'Core local checks passed, but one provider needs an observed run.',
    },
    kpis: { processing_now: 0, waiting: 0, completed_today: 0, needs_attention: 0 },
    services: [
      {
        id: 'uploads',
        name: 'Invoice uploads',
        provider: null,
        status: 'operational',
        uptime: null,
        uptime_label: 'Not enough history',
        observed_at: now,
        activity: '0 invoices stored',
        evidence: 'Current checks passed.',
        affected_capability: null,
        unaffected_capability: null,
      },
      {
        id: 'reader',
        name: 'Document reader',
        provider: 'mistral',
        status: 'unknown',
        uptime: null,
        uptime_label: 'Not enough history',
        observed_at: null,
        activity: 'No observed pipeline run',
        evidence:
          'Configuration is loaded, but no completed workspace run verifies this provider yet.',
        affected_capability: null,
        unaffected_capability: 'Previously processed invoices remain available',
      },
      {
        id: 'extractor',
        name: 'Data extractor',
        provider: 'llm_json',
        status: 'operational',
        uptime: null,
        uptime_label: 'Not enough history',
        observed_at: now,
        activity: '1 completed pipeline run',
        evidence: 'A workspace run completed.',
        affected_capability: null,
        unaffected_capability: 'Previously processed invoices remain available',
      },
      {
        id: 'storage',
        name: 'Document storage',
        provider: null,
        status: 'operational',
        uptime: null,
        uptime_label: 'Not enough history',
        observed_at: now,
        activity: 'Private storage check passed',
        evidence: 'Current storage readiness check.',
        affected_capability: null,
        unaffected_capability: null,
      },
      {
        id: 'accounting_export',
        name: 'Accounting export',
        provider: 'csv_download',
        status: 'operational',
        uptime: null,
        uptime_label: 'Not enough history',
        observed_at: now,
        activity: 'No recorded export run',
        evidence: 'Local export capability is available.',
        affected_capability: null,
        unaffected_capability: 'Invoice review remains available',
      },
    ],
    alerts: [],
    flow: {
      window_label: 'Invoices uploaded on 2026-07-20 UTC',
      denominator: 'Unique invoices from the upload cohort; conversion uses the previous stage.',
      stages: [
        {
          id: 'upload',
          label: 'Upload received',
          count: 0,
          previous_count: null,
          conversion_percent: null,
        },
        { id: 'read', label: 'PDF read', count: 0, previous_count: 0, conversion_percent: null },
        {
          id: 'extract',
          label: 'Data extracted',
          count: 0,
          previous_count: 0,
          conversion_percent: null,
        },
        {
          id: 'checks',
          label: 'Checks completed',
          count: 0,
          previous_count: 0,
          conversion_percent: null,
        },
        {
          id: 'export_attempt',
          label: 'Export attempted',
          count: 0,
          previous_count: 0,
          conversion_percent: null,
        },
        {
          id: 'export_success',
          label: 'Export succeeded',
          count: 0,
          previous_count: 0,
          conversion_percent: null,
        },
      ],
    },
    recent_jobs: [],
    integrations: [
      {
        id: 'reader',
        name: 'Document reader',
        provider: 'mistral',
        status: 'unknown',
        observed_at: null,
        evidence: 'Not observed.',
      },
      {
        id: 'extractor',
        name: 'Data extractor',
        provider: 'llm_json',
        status: 'operational',
        observed_at: now,
        evidence: 'Observed.',
      },
      {
        id: 'storage',
        name: 'File storage',
        provider: null,
        status: 'operational',
        observed_at: now,
        evidence: 'Observed.',
      },
      {
        id: 'accounting_export',
        name: 'Accounting export',
        provider: 'csv_download',
        status: 'operational',
        observed_at: now,
        evidence: 'Available.',
      },
    ],
    audit: [],
    maintenance: {
      scheduled: false,
      title: 'No maintenance scheduled',
      detail: 'This application does not currently manage a maintenance calendar.',
    },
  }
}
