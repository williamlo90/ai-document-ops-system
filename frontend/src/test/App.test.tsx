import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { InvoiceItem, InvoiceListResponse } from '../features/invoices/types'
import type { ReviewWorklist } from '../features/review/types'
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
