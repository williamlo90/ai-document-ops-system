import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({ promise: new Promise(() => {}), destroy: vi.fn() })),
}))

vi.mock('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url', () => ({ default: 'pdf-worker.js' }))

const workspace = {
  workspace_id: 'workspace-test',
  work_items: [],
  pending_approvals: [],
  documents: [],
  metrics: { work_items: 0, pending_approvals: 0, drafts: 0, policy_decisions: 0 },
}

const now = '2026-06-30T10:00:00Z'
const linkedDocument = {
  id: 'doc-1',
  filename: 'acme.pdf',
  status: 'approved',
  created_at: now,
  document_type: 'invoice',
  supported_extraction_schema: 'invoice_v1',
}
const needsReviewDocument = {
  ...linkedDocument,
  status: 'needs_review',
}
const needsCorrectionDocument = {
  ...needsReviewDocument,
  validation_issue_count: 1,
  validation_error_count: 1,
  has_validation_errors: true,
  validation_codes: ['duplicate_invoice'],
}
const workItem = {
  id: 'item-1',
  title: 'Review ACME invoice',
  work_type: 'invoice_review',
  priority: 'normal',
  status: 'awaiting_human',
  linked_document_ids: ['doc-1'],
  business_context: {},
  created_at: now,
  updated_at: now,
  current_plan_id: null,
  assignee: 'Finance reviewer',
  requested_outcome: 'Review safely',
  tags: [],
}
const workItemDetail = {
  ...workItem,
  plans: [],
  current_plan: null,
  drafts: [],
  approvals: [],
  policy_decisions: [],
  activity: [],
}
const workspaceWithLinkedDocument = {
  workspace_id: 'workspace-test',
  work_items: [workItem],
  pending_approvals: [],
  documents: [linkedDocument],
  metrics: { work_items: 1, pending_approvals: 0, drafts: 0, policy_decisions: 0 },
}
const workspaceWithNeedsReviewDocument = {
  ...workspaceWithLinkedDocument,
  work_items: [{ ...workItem, status: 'planning' }],
  documents: [needsReviewDocument],
}
const workspaceWithNeedsCorrectionDocument = {
  ...workspaceWithNeedsReviewDocument,
  documents: [needsCorrectionDocument],
}
const invoiceListWithReviewItem = {
  items: [{
    id: 'doc-1',
    original_filename: 'acme.pdf',
    status: 'awaiting_human',
    created_at: now,
    updated_at: now,
    document_type: 'invoice',
    supported_extraction_schema: 'invoice_v1',
    vendor_name: 'Acme Supplies',
    total: '100.00',
    currency: 'USD',
    current_owner: 'Finance reviewer',
    current_stage: 'waiting_approval',
    work_item_id: 'item-1',
  }],
  page: 1,
  page_size: 8,
  total: 1,
  total_pages: 1,
}
const invoiceListWithCorrectionItem = {
  ...invoiceListWithReviewItem,
  items: [{
    ...invoiceListWithReviewItem.items[0],
    business_status: 'needs_correction',
    validation_issue_count: 1,
    validation_error_count: 1,
    has_validation_errors: true,
    validation_codes: ['duplicate_invoice'],
  }],
}
const plannedWorkItem = {
  ...workItem,
  current_plan_id: 'plan-1',
}
const workspaceWithPlannedWorkItem = {
  ...workspaceWithLinkedDocument,
  work_items: [plannedWorkItem],
}
const pendingApproval = {
  id: 'approval-1',
  work_item_id: 'item-1',
  action_step_id: 'step-1',
  status: 'pending',
  reviewer_notes: null,
  reviewed_by: null,
  reviewed_at: null,
  created_at: now,
}
const pendingApprovalWorkItemDetail = {
  ...workItemDetail,
  current_plan_id: 'plan-1',
  approvals: [pendingApproval],
  policy_decisions: [{
    id: 'policy-1',
    action_step_id: 'step-1',
    action_type: 'invoice_export',
    autonomy_level: 'balanced',
    risk_level: 'high',
    allowed: true,
    requires_confirmation: true,
    reason: 'Exporting an approved invoice changes downstream accounting records.',
  }],
  current_plan: {
    id: 'plan-1',
    planner_version: 'planner-v1',
    overall_confidence: 'medium',
    escalation_reason: 'Accounting export requires reviewer confirmation.',
    requires_human: true,
    created_at: now,
    steps: [{
      id: 'step-1',
      action_type: 'invoice_export',
      risk_level: 'high',
      tool_name: 'accounting_export',
      requires_approval: true,
      status: 'waiting_for_approval',
      why_this: 'Invoice total and vendor evidence are ready for export.',
      why_not: null,
    }],
  },
}
const workspaceWithPendingApproval = {
  ...workspaceWithLinkedDocument,
  work_items: [{ ...workItem, current_plan_id: 'plan-1' }],
  documents: [needsReviewDocument],
  pending_approvals: [pendingApproval],
  metrics: { work_items: 1, pending_approvals: 1, drafts: 0, policy_decisions: 1 },
}
const extractionWithEvidence = {
  document_type: 'invoice',
  schema_version: 'invoice_v1',
  data: {
    vendor_name: 'Acme Logistics',
    invoice_number: 'INV-001',
    invoice_date: '2026-06-18',
    due_date: '2026-07-18',
    total: '100.00',
    currency: 'USD',
    line_items: [],
  },
  validation: [],
  confidence: [{
    field_name: 'invoice_total',
    score: 0.94,
    source_text: 'Invoice total $100.00',
    source_page: 1,
  }],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

describe('application shell', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path === '/operations/notifications') {
        return json({ notifications: [], unread_count: 0 })
      }
      if (path === '/providers/health') {
        return json({ overall_status: 'healthy', providers: [] })
      }
      if (path === '/operations/jobs') {
        return json({ worker: { status: 'healthy' }, jobs: [] })
      }
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    }))
  })

  it('starts in the intake workflow with an accessible role selector', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: /upload and check an invoice/i })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /view application as role/i })).toHaveValue('intake')
    expect(screen.queryByRole('button', { name: /new document task/i })).not.toBeInTheDocument()
  })

  it('switches role and exposes the reviewer approval workspace', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.selectOptions(
      screen.getByRole('combobox', { name: /view application as role/i }),
      'administrator',
    )

    expect((await screen.findAllByRole('heading', { name: /approvals/i })).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /^upload$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /upload invoice/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /invoices/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /approvals/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^history$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /technical evidence/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /system reliability/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /new document task/i })).not.toBeInTheDocument()
    expect(await screen.findByText(/No invoices waiting for approval/i)).toBeInTheDocument()
    expect(screen.getByText(/Uploaded PDFs appear under Invoices first/i)).toBeInTheDocument()
    expect(localStorage.getItem('docops-role')).toBe('administrator')
  })

  it('keeps uploader invoice list status-only', async () => {
    const user = userEvent.setup()
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithLinkedDocument)
      if (path.startsWith('/invoices?')) return json(invoiceListWithReviewItem)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /my invoices/i }))

    expect((await screen.findAllByRole('heading', { name: /my invoices/i })).length).toBeGreaterThan(0)
    expect(screen.getByText(/Acme Supplies/i)).toBeInTheDocument()
    expect(screen.getByText(/View status/i)).toBeInTheDocument()
    expect(screen.queryByText(/Open review/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approvals/i })).not.toBeInTheDocument()
  })

  it('keeps history out of primary navigation', async () => {
    const user = userEvent.setup()
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithLinkedDocument)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    expect((await screen.findAllByRole('button', { name: /upload invoice/i })).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /my invoices/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^history$/i })).not.toBeInTheDocument()

    await user.selectOptions(
      screen.getByRole('combobox', { name: /view application as role/i }),
      'administrator',
    )
    expect(await screen.findByRole('button', { name: /approvals/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^invoices$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^history$/i })).not.toBeInTheDocument()
  })

  it('shows submitted invoices in reviewer approvals when the document needs review', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithNeedsReviewDocument)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))

    expect(await screen.findByText(/Waiting decision \(1\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Needs review/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /review invoice/i })).toBeInTheDocument()
  })

  it('shows correction-required status consistently in the uploader invoice list', async () => {
    localStorage.setItem('docops-role', 'intake')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path.startsWith('/invoices?')) return json(invoiceListWithCorrectionItem)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await screen.findByRole('heading', { name: /upload and check an invoice/i })
    await userEvent.click(screen.getByRole('button', { name: /my invoices/i }))

    expect(await screen.findAllByText(/needs correction/i)).not.toHaveLength(0)
    const statusOptions = screen.getAllByRole('option').map((option) => option.textContent)
    expect(statusOptions.filter((label) => label === 'Reading invoice')).toHaveLength(1)
    expect(statusOptions).toContain('Waiting to be read')
  })

  it('separates invoices with validation blockers from waiting decisions', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithNeedsCorrectionDocument)
      if (path === '/invoices?page=1&page_size=100') return json(invoiceListWithReviewItem)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))

    expect(await screen.findByText(/Waiting decision \(0\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Needs correction \(1\)/i)).toBeInTheDocument()
    await user.click(screen.getByText(/Needs correction \(1\)/i))
    expect(await screen.findByText(/Possible duplicate invoice/i)).toBeInTheDocument()
  })

  it('shows actionable secure session errors without raw implementation detail', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ detail: 'database adapter stack trace' }, 403)
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)

    expect(await screen.findByRole('heading', { name: /unable to verify secure session/i })).toBeInTheDocument()
    expect(screen.getByText(/sign in again before continuing invoice work/i)).toBeInTheDocument()
    expect(screen.queryByText(/database adapter stack trace/i)).not.toBeInTheDocument()
  })

  it('shows a simple invoice review screen without technical tabs', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithNeedsReviewDocument)
      if (path === '/backoffice/work-items/item-1') return json({ work_item: workItemDetail })
      if (path === '/documents/doc-1') return json({ document: needsReviewDocument, extraction: null, audit_events: [] })
      if (path === '/review/doc-1/approve') return json({ status: 'approved' })
      if (path === '/documents/doc-1/workflow') return json({ document: needsReviewDocument, extraction: null, work_item: workItemDetail, current_stage: 'needs_attention', current_owner: 'Finance reviewer', waiting_for: null, next_action: 'Review', attention_reason: null, activity: [] })
      if (path === '/documents/doc-1/content') return Promise.resolve(new Response('%PDF-1.4\n%%EOF', { headers: { 'Content-Type': 'application/pdf' } }))
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))
    await user.click(await screen.findByRole('button', { name: /review invoice/i }))
    expect(await screen.findByText(/INVOICE DATA/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /request correction/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
    expect(screen.queryByText(/Needs review because/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /make decision/i })).not.toBeInTheDocument()

    expect(screen.queryByText('invoice_v1')).not.toBeInTheDocument()
    expect(screen.getAllByText(/invoice/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /open pdf/i })).toHaveAttribute('href', '/documents/doc-1/content')
    expect(document.querySelector('canvas.pdf-canvas')).not.toBeNull()
    expect(document.querySelector('iframe')).toBeNull()

    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/review/doc-1/approve', expect.objectContaining({ method: 'POST' }))

    await user.click(screen.getByRole('button', { name: /back to approvals/i }))
    expect(await screen.findByRole('button', { name: /review invoice/i })).toBeInTheDocument()
  })

  it('explains approval evidence and decision outcomes', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithPendingApproval)
      if (path === '/backoffice/work-items/item-1') return json({ work_item: pendingApprovalWorkItemDetail })
      if (path === '/documents/doc-1') return json({ document: needsReviewDocument, extraction: extractionWithEvidence, audit_events: [] })
      if (path === '/documents/doc-1/workflow') return json({ document: needsReviewDocument, extraction: extractionWithEvidence, work_item: pendingApprovalWorkItemDetail, current_stage: 'needs_attention', current_owner: 'Finance reviewer', waiting_for: 'approval', next_action: 'Review approval', attention_reason: null, activity: [] })
      if (path === '/documents/doc-1/content') return Promise.resolve(new Response('%PDF-1.4\n%%EOF', { headers: { 'Content-Type': 'application/pdf' } }))
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))
    await user.click(await screen.findByRole('button', { name: /review invoice/i }))

    expect(await screen.findByText(/INVOICE DATA/i)).toBeInTheDocument()
    expect(screen.queryByText(/changes downstream accounting records/i)).not.toBeInTheDocument()
    expect(screen.getByText('100.00')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Example: Total and vendor match the PDF.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /request correction/i })).toBeInTheDocument()
  })

  it('keeps technical evidence out of primary administrator navigation', async () => {
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithPlannedWorkItem)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    expect(await screen.findByRole('button', { name: /approvals/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /invoices/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^history$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /technical evidence/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reliability checks/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /test scenarios/i })).not.toBeInTheDocument()
  })
})
