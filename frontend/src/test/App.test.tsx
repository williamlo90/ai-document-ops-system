import { render, screen, waitFor } from '@testing-library/react'
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
const plannedWorkItem = {
  ...workItem,
  current_plan_id: 'plan-1',
}
const plannedWorkItemDetail = {
  ...workItemDetail,
  current_plan_id: 'plan-1',
  current_plan: {
    id: 'plan-1',
    planner_version: 'planner-v1',
    overall_confidence: 'high',
    escalation_reason: null,
    requires_human: false,
    created_at: now,
    steps: [],
  },
}
const workspaceWithPlannedWorkItem = {
  ...workspaceWithLinkedDocument,
  work_items: [plannedWorkItem],
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

    expect(await screen.findByRole('heading', { name: /process a new invoice document/i })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: /view application as role/i })).toHaveValue('intake')
    expect(screen.queryByRole('button', { name: /new document task/i })).not.toBeInTheDocument()
  })

  it('switches role and exposes administrator actions', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.selectOptions(
      screen.getByRole('combobox', { name: /view application as role/i }),
      'administrator',
    )

    expect((await screen.findAllByRole('heading', { name: /work queue/i })).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /work queue/i })).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: /technical evidence/i })[0])
    expect(screen.getByRole('button', { name: /system reliability/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /runtime diagnostics/i })).toBeInTheDocument()
    const createButtons = screen.getAllByRole('button', { name: /new document task/i })
    expect(createButtons.length).toBeGreaterThan(0)
    expect(localStorage.getItem('docops-role')).toBe('administrator')
  })

  it('opens and dismisses the global create-work-item dialog by keyboard', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    render(<App />)

    const create = (await screen.findAllByRole('button', { name: /new document task/i }))[0]
    create.focus()
    await user.keyboard('{Enter}')

    const dialog = await screen.findByRole('dialog', { name: /new document task/i })
    expect(dialog).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /close dialog/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('submits the create-work-item mutation with edited state', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    const fetchMock = vi.mocked(fetch)
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/backoffice/work-items' && init?.method === 'POST') {
        return json({ work_item: { id: 'created-1', title: 'Investigate duplicate invoice' } })
      }
      if (path === '/backoffice/work-items/created-1') {
        return json({
          work_item: {
            id: 'created-1', title: 'Investigate duplicate invoice', work_type: 'invoice_review', priority: 'normal', status: 'new', linked_document_ids: [], business_context: {}, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), assignee: 'Unassigned', requested_outcome: 'Review safely', tags: [], plans: [], current_plan: null, drafts: [], approvals: [], policy_decisions: [], activity: [],
          },
        })
      }
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspace)
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click((await screen.findAllByRole('button', { name: /new document task/i }))[0])
    await user.clear(screen.getByLabelText('Title'))
    await user.type(screen.getByLabelText('Title'), 'Investigate duplicate invoice')
    await user.click(screen.getByRole('button', { name: 'Create Document Task' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/backoffice/work-items',
      expect.objectContaining({ method: 'POST' }),
    ))
  })

  it('shows workspace document schema metadata on linked document records', async () => {
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
    await user.click(await screen.findByText('Review ACME invoice'))
    await user.click(await screen.findByRole('button', { name: /details/i }))

    expect(await screen.findByText('invoice_v1')).toBeInTheDocument()
    expect(screen.getByText('Invoice')).toBeInTheDocument()
  })

  it('shows document operation metadata in evaluation cases', async () => {
    const user = userEvent.setup()
    localStorage.setItem('docops-role', 'administrator')
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/auth/session') return json({ authenticated: true, actor: 'William Lo' })
      if (path === '/backoffice/workspace') return json(workspaceWithPlannedWorkItem)
      if (path === '/backoffice/work-items/item-1') return json({ work_item: plannedWorkItemDetail })
      if (path === '/operations/notifications') return json({ notifications: [], unread_count: 0 })
      if (path === '/providers/health') return json({ overall_status: 'healthy', providers: [] })
      if (path === '/operations/jobs') return json({ worker: { status: 'healthy' }, jobs: [] })
      if (path === '/agentops/runs?limit=50') return json({ runs: [] })
      if (path === '/agentops/scenarios') return json({ dataset_id: 'agentops_core', dataset_version: 'v1', description: 'Agent cases', scenario_count: 0, scenarios: [], required_fields: [] })
      if (path === '/agentops/backoffice/scenarios') {
        return json({
          dataset_id: 'project4_backoffice',
          dataset_version: 'v1',
          description: 'Backoffice cases',
          scenario_count: 1,
          required_fields: ['document_type', 'operation_type'],
          scenarios: [{
            id: 'invoice_review_read_only',
            title: 'Review a linked invoice without mutating state',
            document_type: 'invoice',
            operation_type: 'document_review',
            work_type: 'invoice_review',
            expected_confidence: 'high',
          }],
        })
      }
      if (path === '/agentops/evaluations?limit=100') return json({ evaluations: [] })
      if (path === '/agentops/backoffice/scenarios/evaluate' && init?.method === 'POST') {
        return json({
          result: {
            passed: true,
            checks: { document_type: true, operation_type: true },
            expected_document_type: 'invoice',
            actual_document_type: 'invoice',
            expected_operation_type: 'document_review',
            actual_operation_type: 'document_review',
          },
        })
      }
      return json({ detail: `Unexpected test request: ${path}` }, 404)
    })

    render(<App />)
    await user.click(screen.getAllByRole('button', { name: /technical evidence/i })[0])
    await user.click(await screen.findByRole('button', { name: /reliability checks/i }))

    expect(await screen.findByText('Document: Invoice')).toBeInTheDocument()
    expect(screen.getByText('Operation: Document Review')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /evaluate/i }))
    expect(await screen.findByText(/Actual document: Invoice/)).toBeInTheDocument()
    expect(screen.getByText(/Actual operation: Document Review/)).toBeInTheDocument()
    expect(screen.getByText('Expected document')).toBeInTheDocument()
    expect(screen.getByText('Actual document')).toBeInTheDocument()
    expect(screen.getByText('Expected operation')).toBeInTheDocument()
    expect(screen.getByText('Actual operation')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /test scenarios/i }))
    await user.click(await screen.findByRole('button', { name: /review a linked invoice without mutating state/i }))

    expect(screen.getAllByText('Document: Invoice').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Operation: Document Review').length).toBeGreaterThan(0)
  })
})
