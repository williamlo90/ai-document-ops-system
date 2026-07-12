import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

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
  pending_approvals: [pendingApproval],
  metrics: { work_items: 1, pending_approvals: 1, drafts: 0, policy_decisions: 1 },
}
const extractionWithEvidence = {
  document_type: 'invoice',
  schema_version: 'invoice_v1',
  fields: {},
  line_items: [],
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
    expect(screen.getAllByRole('button', { name: /history/i }).length).toBeGreaterThan(0)
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

  it('shows plain invoice review tabs without exposing schema metadata', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithLinkedDocument)
      if (path === '/backoffice/work-items/item-1') return json({ work_item: workItemDetail })
      if (path === '/documents/doc-1') return json({ document: linkedDocument, extraction: null, audit_events: [] })
      if (path === '/documents/doc-1/workflow') return json({ document: linkedDocument, extraction: null, work_item: workItemDetail, current_stage: 'needs_attention', current_owner: 'Finance reviewer', waiting_for: null, next_action: 'Review', attention_reason: null, activity: [] })
      if (path === '/documents/doc-1/content') return Promise.resolve(new Response('%PDF-1.4\n%%EOF', { headers: { 'Content-Type': 'application/pdf' } }))
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))
    await user.click(await screen.findByRole('button', { name: /review invoice/i }))
    await user.click(await screen.findByRole('button', { name: /make decision/i }))
    expect(await screen.findByText(/Needs review because/i)).toBeInTheDocument()
    expect(screen.getByText(/Waiting for reviewer decision/i)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /check invoice/i }).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /make decision/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /history/i }).length).toBeGreaterThan(0)

    expect(screen.queryByText('invoice_v1')).not.toBeInTheDocument()
    expect(screen.getAllByText(/invoice/i).length).toBeGreaterThan(0)
  })

  it('explains approval evidence and decision outcomes', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithPendingApproval)
      if (path === '/backoffice/work-items/item-1') return json({ work_item: pendingApprovalWorkItemDetail })
      if (path === '/documents/doc-1') return json({ document: linkedDocument, extraction: extractionWithEvidence, audit_events: [] })
      if (path === '/documents/doc-1/workflow') return json({ document: linkedDocument, extraction: extractionWithEvidence, work_item: pendingApprovalWorkItemDetail, current_stage: 'needs_attention', current_owner: 'Finance reviewer', waiting_for: 'approval', next_action: 'Review approval', attention_reason: null, activity: [] })
      if (path === '/documents/doc-1/content') return Promise.resolve(new Response('%PDF-1.4\n%%EOF', { headers: { 'Content-Type': 'application/pdf' } }))
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(await screen.findByRole('button', { name: /approvals/i }))
    await user.click(await screen.findByRole('button', { name: /review invoice/i }))
    await user.click(await screen.findByRole('button', { name: /make decision/i }))

    expect((await screen.findAllByText(/Decision Needed/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/changes downstream accounting records/i).length).toBeGreaterThan(0)
    expect(screen.getByText('Invoice total $100.00')).toBeInTheDocument()
    expect(screen.getByText(/Approve only when the invoice details match the PDF/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'What did you check?')
    expect(screen.getByRole('button', { name: /approve invoice/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask for correction/i })).toBeInTheDocument()
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
    expect(screen.getByRole('button', { name: /history/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /technical evidence/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reliability checks/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /test scenarios/i })).not.toBeInTheDocument()
  })
})
