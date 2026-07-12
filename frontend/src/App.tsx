import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bell,
  Boxes,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleGauge,
  ClipboardCheck,
  Columns3,
  Database,
  FileCheck2,
  FileClock,
  FileText,
  Filter,
  Inbox,
  Link2,
  ListChecks,
  Loader2,
  Menu,
  MoreHorizontal,
  Network,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  UserRound,
  Workflow,
  X,
  Zap,
} from 'lucide-react'
import { useEffect, useState } from 'react'

type Metrics = { work_items: number; pending_approvals: number; drafts: number; policy_decisions: number }
type DocumentSummary = { id: string; filename: string; status: string; created_at: string; document_type?: string; supported_extraction_schema?: string }
type WorkItemSummary = {
  id: string
  title: string
  work_type: string | null
  priority: string
  status: string
  linked_document_ids: string[]
  business_context: Record<string, string>
  created_at: string
  updated_at: string
  current_plan_id?: string | null
  assignee: string
  requested_outcome: string
  tags: string[]
}
type ActionStep = {
  id: string
  action_type: string
  risk_level: string
  tool_name: string | null
  requires_approval: boolean
  status: string
  why_this: string | null
  why_not: string | null
}
type TaskPlan = {
  id: string
  planner_version: string
  overall_confidence: string
  escalation_reason: string | null
  requires_human: boolean
  created_at: string
  steps: ActionStep[]
  agent_run_id?: string | null
}
type Draft = {
  id: string
  action_step_id: string | null
  draft_type: string
  status: string
  preview_content: string
  created_at: string
  updated_at: string
}
type Approval = {
  id: string
  work_item_id: string
  action_step_id: string | null
  status: string
  reviewer_notes: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
}
type PolicyDecision = {
  id: string
  action_step_id: string | null
  action_type: string
  autonomy_level: string
  risk_level: string
  allowed: boolean
  requires_confirmation: boolean
  reason: string
}
type WorkItemDetail = WorkItemSummary & {
  plans: TaskPlan[]
  current_plan: TaskPlan | null
  drafts: Draft[]
  approvals: Approval[]
  policy_decisions: PolicyDecision[]
  activity: WorkflowActivity[]
}
type Workspace = {
  workspace_id: string
  work_items: WorkItemSummary[]
  pending_approvals: Approval[]
  documents: DocumentSummary[]
  metrics: Metrics
}
type LineItem = { description?: string | null; quantity?: string | null; unit_price?: string | null; amount?: string | null }
type Extraction = {
  document_type?: string
  schema_version?: string
  data?: Record<string, unknown>
  confidence?: Array<{ field_name: string; score: number | null; source_page?: number | null; source_text?: string | null }>
  validation?: Array<{ field?: string; field_name?: string; message?: string; severity?: string }>
}
type ApiDocument = { id: string; original_filename: string; status: string; created_at: string; updated_at?: string; error_message?: string | null; submitted_by?: string; size_bytes?: number; document_type?: string; supported_extraction_schema?: string }
type InvoiceListItem = ApiDocument & { vendor_name?: string | null; total?: string | null; currency?: string | null; current_owner: string; current_stage: string; work_item_id?: string | null }
type InvoiceList = { items: InvoiceListItem[]; page: number; page_size: number; total: number; total_pages: number }
type DocumentDetail = { document: ApiDocument; extraction: Extraction | null; audit_events: Array<{ id?: string; event_type?: string; created_at?: string; payload_summary?: string }> }
type WorkflowActivity = { id: string; event_type: string; actor: string; summary: string; source: string; document_id?: string | null; work_item_id?: string | null; agent_run_id?: string | null; created_at: string }
type DocumentWorkflow = {
  document: ApiDocument
  extraction: Extraction | null
  work_item: WorkItemDetail | null
  current_stage: string
  current_owner: string
  waiting_for: string | null
  next_action: string
  attention_reason: string | null
  activity: WorkflowActivity[]
}
type UserRole = 'intake' | 'administrator'
type IntakeView = 'new' | 'submissions' | 'invoices' | 'guide'
type PageId = 'runs' | 'drafts' | 'approvals' | 'operations' | 'policies' | 'guardrails' | 'integrations' | 'settings' | 'reliability' | 'evaluation' | 'datasets'
type Screen = { kind: 'overview' } | { kind: 'queue'; filter?: QueueFilter } | { kind: 'workitems' } | { kind: 'detail'; id: string } | { kind: 'documents' } | { kind: 'page'; page: PageId } | { kind: 'intake'; view: IntakeView }
type QueueFilter = 'all' | 'attention' | 'progress' | 'approval' | 'completed' | 'blocked'
type AgentRun = {
  id: string
  actor: string
  request: string
  intent: string
  prompt_version: string
  created_at: string
  work_item_id?: string | null
  plan_id?: string | null
  latency_ms?: number | null
  evaluation: {
    expected_tool: string | null
    selected_tool: string | null
    tool_selection_correct: boolean | null
    confidence: string
    confidence_score: number
    failure_type: string | null
    human_escalated: boolean
    blocked_action_count: number
    tool_call_count: number
    estimated_cost_usd: number | null
    successful_completion: boolean
    decision_reason: string
  }
}
type ReliabilitySummary = {
  total_runs: number
  evaluated_runs: number
  tool_selection_accuracy: number | null
  unsafe_action_prevention_rate: number | null
  successful_completion_rate: number | null
  escalation_rate: number | null
  average_confidence: number | null
  average_tool_calls_per_task: number | null
  average_latency_ms: number | null
  estimated_cost_per_run: number | null
  confidence_distribution: Record<string, number>
  failure_counts: Record<string, number>
  failure_trend?: Array<{ failure_type: string; count: number }>
}
type ProviderHealth = {
  overall_status: string
  providers: Array<{ role: string; provider_name: string; status: string; configuration_ready: boolean; observed_runs: number; observed_failures: number; evidence: string }>
}
type IntegrationStatus = { integrations: Array<{ name: string; provider: string; status: string; configuration_ready: boolean; sandbox_mode: boolean; evidence: string }> }
type NotificationItem = { id: string; notification_type: string; title: string; message: string; severity: string; work_item_id?: string | null; document_id?: string | null; read_at?: string | null; created_at: string }
type NotificationFeed = { unread_count: number; notifications: NotificationItem[] }
type OperationsJobs = { worker: { status: string; queued_jobs: number; failed_jobs: number; stalled_jobs: number; evidence: string }; failed_jobs: Array<{ id: string; document_id: string; status: string; attempt_count: number; error_message?: string | null; provider_name?: string | null }> }
type ExceptionFilter = 'all' | 'missing_information' | 'validation_failure' | 'waiting_approval' | 'blocked' | 'failed'
type Scenario = {
  id: string
  title?: string
  message?: string
  document_type?: string
  operation_type?: string
  work_type?: string
  expected_tool?: string
  expected_risk?: string
  expected_outcome?: string
  expected_requires_human?: boolean
  expected_confidence?: string
  expected_plan_steps?: string[]
  prompt_version?: string
}
type ScenarioDataset = {
  dataset_id: string
  dataset_version: string
  description: string
  scenario_count: number
  scenarios: Scenario[]
  required_fields?: string[]
}
type ScenarioResult = { passed: boolean; checks: Record<string, boolean>; actual_document_type?: string; actual_operation_type?: string; expected_document_type?: string; expected_operation_type?: string }
type ScenarioEvaluation = { scenario_id: string; passed: boolean; evidence: Partial<ScenarioResult>; created_at: string }
type Regression = { deltas: Array<{ metric: string; previous: number | null; current: number | null; delta: number | null; regressed: boolean }>; improved_metrics: string[]; regressed_metrics: string[] }
type PromptVersionMetric = { prompt_version: string; total_runs: number; evaluated_runs: number; tool_selection_accuracy: number | null; escalation_rate: number; average_confidence: number | null; estimated_cost_per_run: number | null }

const queryClient = new QueryClient()
const PRODUCT_NAME = 'AI Document Ops System'
const workTypes = ['invoice_review', 'invoice_export', 'accounting_note', 'vendor_follow_up', 'exception_handling', 'insufficient_evidence']

function api<T>(path: string, init?: RequestInit): Promise<T> {
  return fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail ?? `Request failed with ${response.status}`)
    return payload as T
  })
}

function uploadApi<T>(path: string, body: FormData, onProgress?: (progress: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('POST', path)
    request.withCredentials = true
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    request.onerror = () => reject(new Error('Upload failed because the server could not be reached.'))
    request.onload = () => {
      let payload: Record<string, unknown> = {}
      try { payload = JSON.parse(request.responseText) as Record<string, unknown> } catch { /* handled below */ }
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(String(payload.detail ?? `Request failed with ${request.status}`)))
        return
      }
      resolve(payload as T)
    }
    request.send(body)
  })
}

function App() {
  return <QueryClientProvider client={queryClient}><SessionGate /></QueryClientProvider>
}

function SessionGate() {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const session = useQuery({
    queryKey: ['auth-session'],
    queryFn: async () => {
      const response = await fetch('/auth/session', { credentials: 'same-origin' })
      if (response.status === 401) return null
      if (!response.ok) throw new Error('Unable to verify the secure session.')
      return response.json() as Promise<{ authenticated: boolean; actor: string }>
    },
    retry: false,
  })
  const login = useMutation({
    mutationFn: () => api('/auth/session', { method: 'POST', body: JSON.stringify({ admin_token: token }) }),
    onSuccess: () => {
      setToken('')
      setError('')
      queryClient.invalidateQueries({ queryKey: ['auth-session'] })
    },
    onError: (loginError: Error) => setError(loginError.message),
  })
  if (session.isLoading) return <LoadingState />
  if (session.error) return <ErrorState message={session.error.message} retry={() => session.refetch()} />
  if (!session.data?.authenticated) {
    return <main className="session-login"><section className="data-panel settings-panel"><span className="brand-mark"><ShieldCheck size={22} /></span><h1>Sign in securely</h1><p>The admin credential is exchanged once for an opaque HttpOnly session cookie. It is not stored in the browser.</p><label><span>Local admin token</span><input type="password" autoComplete="current-password" value={token} onChange={(event) => setToken(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && token) login.mutate() }} /></label><button className="primary-button" disabled={!token || login.isPending} onClick={() => login.mutate()}>{login.isPending ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />} Sign in</button>{error ? <div className="notice danger"><AlertTriangle size={15} /><p>{error}</p></div> : null}</section></main>
  }
  return <CommandCenter />
}

function CommandCenter() {
  const [role, setRole] = useState<UserRole>(() => (localStorage.getItem('docops-role') as UserRole | null) ?? 'intake')
  const [screen, setScreen] = useState<Screen>(() => role === 'intake' ? { kind: 'intake', view: 'new' } : { kind: 'queue' })
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [globalCreateOpen, setGlobalCreateOpen] = useState(false)
  const workspace = useQuery({
    queryKey: ['workspace'],
    queryFn: () => api<Workspace>('/backoffice/workspace'),
    refetchInterval: 10000,
  })
  const goQueue = (filter?: QueueFilter) => setScreen({ kind: 'queue', filter })
  const goAllWork = () => setScreen({ kind: 'workitems' })
  const openItem = (id: string) => setScreen({ kind: 'detail', id })
  const goPage = (page: PageId) => setScreen({ kind: 'page', page })
  const changeRole = (nextRole: UserRole) => {
    localStorage.setItem('docops-role', nextRole)
    setRole(nextRole)
    setScreen(nextRole === 'intake' ? { kind: 'intake', view: 'new' } : { kind: 'queue' })
  }
  const attentionCount = workspace.data?.work_items.filter((item) => ['awaiting_human', 'blocked', 'failed'].includes(item.status)).length ?? 0

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        screen={screen}
        close={() => setSidebarOpen(false)}
        goQueue={goQueue}
        goAllWork={goAllWork}
        goPage={goPage}
        inboxCount={attentionCount}
        role={role}
        goIntake={(view) => setScreen({ kind: 'intake', view })}
        goOverview={() => setScreen({ kind: 'overview' })}
      />
      <div className="app-main">
        <TopBar
          screen={screen}
          openMenu={() => setSidebarOpen(true)}
          goQueue={goQueue}
          healthy={!workspace.error}
          role={role}
          changeRole={changeRole}
          newWorkItem={() => setGlobalCreateOpen(true)}
          openItem={openItem}
          openDocuments={() => setScreen({ kind: 'documents' })}
        />
        {workspace.error ? (
          <ErrorState message={(workspace.error as Error).message} retry={() => workspace.refetch()} />
        ) : screen.kind === 'intake' ? (
          screen.view === 'new' ? <GuidedInvoiceWizard onSubmitted={openItem} /> : <IntakeLibrary view={screen.view} openItem={openItem} />
        ) : screen.kind === 'overview' ? (
          <OperationsOverview workspace={workspace.data} loading={workspace.isLoading} openItem={openItem} goQueue={goQueue} />
        ) : screen.kind === 'detail' ? (
          <WorkItemPage
            itemId={screen.id}
            workspace={workspace.data}
            loadingWorkspace={workspace.isLoading}
            openItem={openItem}
          />
        ) : screen.kind === 'workitems' ? (
          <QueuePage workspace={workspace.data} loading={workspace.isLoading} openItem={openItem} exceptionMode />
        ) : screen.kind === 'documents' ? (
          <DocumentsPage workspace={workspace.data} loading={workspace.isLoading} />
        ) : screen.kind === 'page' ? (
          <SectionPage page={screen.page} workspace={workspace.data} loadingWorkspace={workspace.isLoading} openItem={openItem} />
        ) : (
          <QueuePage workspace={workspace.data} loading={workspace.isLoading} openItem={openItem} attentionOnly initialFilter={screen.filter} />
        )}
        <footer className="app-footer">
          <span><ShieldCheck size={14} /> All actions are logged and auditable.</span>
          <span>Local Mode <i /> Data stays on your machine</span>
        </footer>
        {globalCreateOpen ? <CreateWorkItemModal documents={workspace.data?.documents ?? []} close={() => setGlobalCreateOpen(false)} openItem={openItem} /> : null}
      </div>
    </div>
  )
}

function Sidebar({
  open,
  screen,
  close,
  goQueue,
  goAllWork,
  goPage,
  inboxCount,
  role,
  goIntake,
  goOverview,
}: {
  open: boolean
  screen: Screen
  close: () => void
  goQueue: () => void
  goAllWork: () => void
  goPage: (page: PageId) => void
  inboxCount: number
  role: UserRole
  goIntake: (view: IntakeView) => void
  goOverview: () => void
}) {
  const activeGroup =
    screen.kind === 'page'
      ? pageGroup(screen.page)
      : screen.kind === 'queue' || screen.kind === 'workitems' || screen.kind === 'detail' || screen.kind === 'overview'
        ? 'Daily Work'
        : 'System Setup'
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({
    'Daily Work': activeGroup === 'Daily Work',
    'Safety Rules': activeGroup === 'Safety Rules',
    'System Setup': activeGroup === 'System Setup',
    'Technical Evidence': activeGroup === 'Technical Evidence',
  })
  useEffect(() => {
    setExpandedGroups((current) => ({ ...current, [activeGroup]: true }))
  }, [activeGroup])
  const groups = [
    {
      label: 'Daily Work',
      icon: Inbox,
      items: [
        [CircleGauge, 'Work Summary', goOverview, screen.kind === 'overview'],
        [Inbox, 'Work Queue', goQueue, screen.kind === 'queue'],
        [ListChecks, 'Exceptions', goAllWork, screen.kind === 'workitems' || screen.kind === 'detail'],
        [FileClock, 'Drafts', () => goPage('drafts'), screen.kind === 'page' && screen.page === 'drafts'],
        [ClipboardCheck, 'Approvals', () => goPage('approvals'), screen.kind === 'page' && screen.page === 'approvals'],
      ],
    },
    {
      label: 'Safety Rules',
      icon: ShieldCheck,
      items: [[FileCheck2, 'Policy Rules', () => goPage('policies'), screen.kind === 'page' && screen.page === 'policies'], [ShieldCheck, 'Safety Boundaries', () => goPage('guardrails'), screen.kind === 'page' && screen.page === 'guardrails']],
    },
    {
      label: 'System Setup',
      icon: Network,
      items: [[Network, 'Integrations', () => goPage('integrations'), screen.kind === 'page' && screen.page === 'integrations'], [Settings, 'Settings', () => goPage('settings'), screen.kind === 'page' && screen.page === 'settings']],
    },
    {
      label: 'Technical Evidence',
      icon: CircleGauge,
      items: [
        [CircleGauge, 'System Reliability', () => goPage('reliability'), screen.kind === 'page' && screen.page === 'reliability'],
        [Workflow, 'Reliability Checks', () => goPage('evaluation'), screen.kind === 'page' && screen.page === 'evaluation'],
        [Database, 'Test Scenarios', () => goPage('datasets'), screen.kind === 'page' && screen.page === 'datasets'],
        [Activity, 'Run Traces', () => goPage('runs'), screen.kind === 'page' && screen.page === 'runs'],
        [CircleGauge, 'Runtime Diagnostics', () => goPage('operations'), screen.kind === 'page' && screen.page === 'operations'],
      ],
    },
  ] as const

  if (role === 'intake') {
    const intakeItems = [
      [Upload, 'New Document', () => goIntake('new'), screen.kind === 'intake' && screen.view === 'new'],
      [FileClock, 'My Documents', () => goIntake('submissions'), screen.kind === 'intake' && screen.view === 'submissions'],
      [FileText, 'Document Library', () => goIntake('invoices'), screen.kind === 'intake' && screen.view === 'invoices'],
      [ListChecks, 'Processing Guide', () => goIntake('guide'), screen.kind === 'intake' && screen.view === 'guide'],
    ] as const
    return (
      <>
        {open ? <button className="sidebar-scrim" aria-label="Close menu" onClick={close} /> : null}
        <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
          <div className="brand"><div className="brand-mark"><Sparkles size={23} /></div><div><strong>{PRODUCT_NAME}</strong><span>Document Intake</span></div></div>
          <nav className="sidebar-nav intake-nav">
            <p className="role-nav-label">DOCUMENT WORK</p>
            {intakeItems.map(([Icon, label, action, active]) => <button key={label} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => { action(); close() }}><Icon size={19} /><span>{label}</span></button>)}
          </nav>
          <div className="intake-role-card"><UserRound size={18} /><div><span>Current role</span><strong>Intake Operator</strong></div></div>
        </aside>
      </>
    )
  }

  return (
    <>
      {open ? <button className="sidebar-scrim" aria-label="Close menu" onClick={close} /> : null}
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Sparkles size={23} /></div>
          <div><strong>{PRODUCT_NAME}</strong><span>Operations Console</span></div>
        </div>
        <nav className="sidebar-nav">
          {groups.map((group) => (
            <div className="nav-group" key={group.label}>
              <button
                className={`nav-group-toggle ${activeGroup === group.label ? 'current' : ''}`}
                onClick={() => setExpandedGroups((current) => ({ ...current, [group.label]: !current[group.label] }))}
                aria-expanded={expandedGroups[group.label]}
              >
                <group.icon size={18} />
                <span>{group.label}</span>
                <ChevronDown className={expandedGroups[group.label] ? 'expanded' : ''} size={16} />
              </button>
              {expandedGroups[group.label] ? (
                <div className="nav-children">
                  {group.items.map(([Icon, label, action, active]) => (
                    <button key={label} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => { action(); close() }}>
                      <Icon size={18} /><span>{label}</span>
                      {label === 'Work Queue' ? <b>{inboxCount}</b> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </nav>
        <div className="autonomy-card">
          <span>Execution Policy</span>
          <strong>Balanced</strong>
          <small>Approval gated</small>
          <p>Confirmation required for risky execution</p>
          <button onClick={() => { goPage('policies'); close() }}>View policy</button>
        </div>
      </aside>
    </>
  )
}

function TopBar({
  screen,
  openMenu,
  goQueue,
  healthy,
  role,
  changeRole,
  newWorkItem,
  openItem,
  openDocuments,
}: {
  screen: Screen
  openMenu: () => void
  goQueue: () => void
  healthy: boolean
  role: UserRole
  changeRole: (role: UserRole) => void
  newWorkItem: () => void
  openItem: (id: string) => void
  openDocuments: () => void
}) {
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const notifications = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api<NotificationFeed>('/operations/notifications'),
    enabled: role === 'administrator',
    refetchInterval: 10000,
  })
  const markRead = useMutation({
    mutationFn: (id: string) => api(`/operations/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const markAll = useMutation({
    mutationFn: () => api('/operations/notifications/read-all', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const follow = (item: NotificationItem) => {
    if (!item.read_at) markRead.mutate(item.id)
    setNotificationsOpen(false)
    if (item.work_item_id) openItem(item.work_item_id)
    else if (item.document_id) openDocuments()
  }
  return (
    <header className="topbar">
      <div className="topbar-title">
        <button className="mobile-menu" onClick={openMenu} aria-label="Open navigation"><Menu size={20} /></button>
        {screen.kind === 'detail' ? (
          <><h1>Document Workspace</h1><button className="back-link" onClick={goQueue}><ArrowLeft size={14} /> Back to queue</button></>
        ) : <h1>{screen.kind === 'intake' ? intakeTitle(screen.view) : screen.kind === 'overview' ? 'Work Summary' : screen.kind === 'workitems' ? 'Exception Queue' : screen.kind === 'documents' ? 'Document Library' : screen.kind === 'page' ? pageTitle(screen.page) : 'Work Queue'}</h1>}
      </div>
      <div className="topbar-actions">
        <span className={`health ${healthy ? '' : 'unhealthy'}`}><ShieldCheck size={15} /> {healthy ? 'System healthy' : 'API unavailable'}</span>
        {role === 'administrator' ? <button className="outline-button" onClick={() => window.open('/ui/agentops', '_blank')}><Boxes size={15} /> Technical Evidence</button> : null}
        {role === 'administrator' ? <button className="primary-button topbar-create" onClick={newWorkItem}><Plus size={15} /> New Document Task</button> : null}
        {role === 'administrator' ? <div className="notification"><button className="icon-button" aria-label="Notifications" onClick={() => setNotificationsOpen((value) => !value)}><Bell size={18} />{notifications.data?.unread_count ? <b>{notifications.data.unread_count}</b> : null}</button>{notificationsOpen ? <section className="notification-popover"><header><strong>Notifications</strong><button className="outline-button" disabled={!notifications.data?.unread_count || markAll.isPending} onClick={() => markAll.mutate()}>Mark all read</button></header>{notifications.isLoading ? <LoadingState /> : notifications.error ? <p>{notifications.error.message}</p> : notifications.data?.notifications.length ? notifications.data.notifications.map((item) => <button className={item.read_at ? '' : 'unread'} key={item.id} onClick={() => follow(item)}><span className={`activity-dot ${item.severity}`}><Bell size={12} /></span><div><strong>{item.title}</strong><p>{item.message}</p><small>{relativeTime(item.created_at)}</small></div></button>) : <EmptyState title="No notifications" body="Operational events will appear here." />}</section> : null}</div> : null}
        <span className="avatar">W</span>
        <div className="operator"><strong>William Lo</strong><span>{role === 'intake' ? 'Intake Operator' : 'Administrator / Reviewer'}</span></div>
        <select className="role-select" value={role} onChange={(event) => changeRole(event.target.value as UserRole)} aria-label="View application as role" title="Demo view only; backend role enforcement is not enabled">
          <option value="intake">Intake Operator</option>
          <option value="administrator">Administrator / Reviewer</option>
        </select>
      </div>
    </header>
  )
}

function GuidedInvoiceWizard({ onSubmitted }: { onSubmitted: (workItemId: string) => void }) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [documentId, setDocumentId] = useState(() => localStorage.getItem('active-invoice-document') ?? '')
  const [outcome, setOutcome] = useState('invoice_review')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [resumeChecked, setResumeChecked] = useState(false)
  const [processMessage, setProcessMessage] = useState('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [submittedItem, setSubmittedItem] = useState<WorkItemSummary | null>(null)
  const [lineItems, setLineItems] = useState<LineItem[]>([])
  const [pdfUrl, setPdfUrl] = useState('')
  const detail = useQuery({
    queryKey: ['guided-document', documentId],
    queryFn: () => api<DocumentDetail>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
  })

  useEffect(() => {
    const data = detail.data?.extraction?.data
    if (!data) return
    setFields(Object.fromEntries(['vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'subtotal', 'tax', 'total', 'currency'].map((key) => [key, String(data[key] ?? '')])))
    setLineItems(Array.isArray(data.line_items) ? data.line_items as LineItem[] : [])
  }, [detail.data])

  useEffect(() => {
    if (file) {
      const url = URL.createObjectURL(file)
      setPdfUrl(url)
      return () => URL.revokeObjectURL(url)
    }
    if (!documentId) return
    let active = true
    fetch(`/documents/${documentId}/content`, { credentials: 'same-origin' })
      .then((response) => {
        if (!response.ok) throw new Error('Preview unavailable')
        return response.blob()
      })
      .then((blob) => {
        if (!active) return
        const url = URL.createObjectURL(blob)
        setPdfUrl(url)
      })
      .catch(() => setPdfUrl(''))
    return () => { active = false }
  }, [file, documentId])

  const uploadPolicy = useQuery({
    queryKey: ['upload-policy', file?.name, file?.size],
    queryFn: () => api<{ max_upload_bytes: number; duplicates: ApiDocument[] }>(`/documents/upload-policy?filename=${encodeURIComponent(file?.name ?? '')}&size_bytes=${file?.size ?? 0}`),
    enabled: Boolean(file),
  })

  useEffect(() => {
    if (!detail.data || resumeChecked) return
    const status = detail.data.document.status
    if (['extracted', 'needs_review', 'approved'].includes(status)) setStep(2)
    else if (['queued', 'processing', 'failed'].includes(status)) setStep(1)
    setResumeChecked(true)
  }, [detail.data, resumeChecked])

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a PDF invoice first.')
      const body = new FormData()
      body.append('file', file)
      setUploadProgress(1)
      return uploadApi<{ document: ApiDocument }>('/documents/upload', body, setUploadProgress)
    },
    onSuccess: ({ document }) => {
      localStorage.setItem('active-invoice-document', document.id)
      setDocumentId(document.id)
      setResumeChecked(true)
      setStep(1)
      setUploadProgress(100)
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
  const processMutation = useMutation({
    mutationFn: () => api<{ document: ApiDocument }>(`/documents/${documentId}/process`, { method: 'POST' }),
    onSuccess: async ({ document: processed }) => {
      const refreshed = await detail.refetch()
      const status = refreshed.data?.document.status ?? processed.status
      if (['extracted', 'needs_review', 'approved'].includes(status)) {
        setProcessMessage('')
        setStep(2)
      } else {
        setProcessMessage(status === 'failed' ? 'Extraction failed. Review the document event and try again.' : 'Processing is queued. Retry after the worker becomes available.')
      }
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
  const cancelMutation = useMutation({
    mutationFn: () => api(`/documents/${documentId}/cancel`, { method: 'POST' }),
    onSuccess: () => {
      localStorage.removeItem('active-invoice-document')
      setDocumentId('')
      setFile(null)
      setFields({})
      setLineItems([])
      setStep(0)
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
  const reprocessMutation = useMutation({
    mutationFn: () => api(`/documents/${documentId}/reprocess`, { method: 'POST' }),
    onSuccess: async () => {
      await detail.refetch()
      setStep(1)
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
    },
  })
  const draftPayload = () => ({
    vendor_name: fields.vendor_name || null,
    invoice_number: fields.invoice_number || null,
    invoice_date: fields.invoice_date || null,
    due_date: fields.due_date || null,
    subtotal: fields.subtotal || null,
    tax: fields.tax || null,
    total: fields.total || null,
    currency: fields.currency || null,
    line_items: lineItems.map((item) => ({
      description: item.description || null,
      quantity: item.quantity || null,
      unit_price: item.unit_price || null,
      amount: item.amount || null,
    })),
  })
  const saveDraftMutation = useMutation({
    mutationFn: () => api(`/invoices/${documentId}/draft`, { method: 'POST', body: JSON.stringify(draftPayload()) }),
    onSuccess: () => detail.refetch(),
  })
  const submitMutation = useMutation({
    mutationFn: async () => {
      await api(`/invoices/${documentId}/draft`, { method: 'POST', body: JSON.stringify(draftPayload()) })
      const selected = workTypes.find((type) => type === outcome) ?? 'invoice_review'
      const workspace = await api<Workspace>('/backoffice/workspace')
      const existing = workspace.work_items.find((item) => item.linked_document_ids.includes(documentId))
      const created = existing ? { work_item: existing } : await api<{ work_item: WorkItemSummary }>('/backoffice/work-items', { method: 'POST', headers: { 'Idempotency-Key': `invoice-submit:${documentId}:${selected}` }, body: JSON.stringify({ title: invoiceTitle(selected, fields), work_type: selected, linked_document_ids: [documentId], requested_outcome: outcomeCopy(selected) }) })
      if (!existing?.current_plan_id) await api(`/backoffice/work-items/${created.work_item.id}/plan`, { method: 'POST', headers: { 'Idempotency-Key': `invoice-plan:${documentId}:${selected}` }, body: JSON.stringify({ requested_outcome: outcomeCopy(selected) }) })
      return created.work_item
    },
    onSuccess: (item) => {
      localStorage.removeItem('active-invoice-document')
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      setSubmittedItem(item)
      setStep(4)
    },
  })

  const steps = ['Upload', 'Extract', 'Verify', 'Submit']
  const document = detail.data?.document
  const validation = detail.data?.extraction?.validation ?? []
  const arithmeticIssues = invoiceArithmeticIssues(fields, lineItems)
  const duplicate = uploadPolicy.data?.duplicates?.[0]
  const maxBytes = uploadPolicy.data?.max_upload_bytes ?? 15 * 1024 * 1024
  return (
    <main className="guided-page">
      <section className="guided-heading"><div><span>DOCUMENT INTAKE</span><h2>Process a new invoice document</h2><p>Follow four guided steps. This workflow currently supports invoice PDFs and creates a bounded document task for review.</p></div><WorkflowOrientation step={steps[Math.min(step, 3)]} owner={step < 3 ? 'Intake Operator' : 'AI Workflow'} waiting={step === 0 ? 'Invoice PDF' : undefined} next={step === 0 ? 'Upload invoice' : step === 1 ? 'Run extraction' : step === 2 ? 'Verify extracted data' : 'Submit for processing'} /></section>
      <div className="wizard-stepper">{steps.map((label, index) => <div className={index < step ? 'complete' : index === step ? 'active' : ''} key={label}><span>{index < step ? <Check size={15} /> : index + 1}</span><strong>{label}</strong></div>)}</div>
      <section className="wizard-card">
        {step === 0 ? <div className="upload-layout"><div className="upload-step"><label className="upload-zone"><Upload size={32} /><strong>{file?.name ?? 'Choose an invoice PDF'}</strong><span>PDF only, up to {formatBytes(maxBytes)}.</span>{file ? <small>{formatBytes(file.size)} · ready to upload</small> : null}<input type="file" accept="application/pdf,.pdf" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setUploadProgress(0) }} /></label>{duplicate ? <div className="duplicate-warning"><AlertTriangle size={16} /><span><strong>Possible duplicate</strong>A file with the same name and size was submitted {formatDate(duplicate.created_at)}.</span></div> : null}{uploadMutation.isPending ? <div className="upload-progress"><span style={{ width: `${uploadProgress}%` }} /><strong>{uploadProgress}% uploaded</strong></div> : null}<button className="primary-button wizard-primary" disabled={!file || file.size > maxBytes || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>{uploadMutation.isPending ? <Loader2 className="spin" size={17} /> : <Upload size={17} />} Upload & Continue</button>{uploadMutation.error ? <p className="wizard-error">{(uploadMutation.error as Error).message}</p> : null}</div><PdfPreview url={pdfUrl} filename={file?.name ?? ''} /></div> : null}
        {step === 1 ? <div className="extract-step"><StageActivity events={detail.data?.audit_events ?? []} active={processMutation.isPending} /><div className="wizard-actions"><button className="danger-outline-button" disabled={cancelMutation.isPending || !['queued','failed'].includes(document?.status ?? '')} onClick={() => cancelMutation.mutate()}><X size={16} /> Cancel Intake</button><button className="primary-button" disabled={processMutation.isPending || document?.status === 'failed'} onClick={() => { setProcessMessage(''); processMutation.mutate() }}>{processMutation.isPending ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />} Extract Invoice Data</button></div>{processMessage ? <p className="wizard-error">{processMessage}</p> : null}{processMutation.error ? <p className="wizard-error">{(processMutation.error as Error).message}</p> : null}{cancelMutation.error ? <p className="wizard-error">{(cancelMutation.error as Error).message}</p> : null}</div> : null}
        {step === 2 ? <div className="verification-layout"><PdfPreview url={pdfUrl} filename={document?.original_filename ?? ''} /><div className="verify-step"><div className="verify-header"><div><Status value={document?.status ?? 'processing'} /><h3>Verify extracted data</h3><p>Compare every value with the source PDF before continuing.</p></div><span className="confidence">{detail.data?.extraction?.confidence?.length ?? 0} evidence fields</span></div><div className="verify-grid">{guidedFields.map(([key, label, type]) => { const evidence = detail.data?.extraction?.confidence?.find((item) => item.field_name === key); return <label key={key}><span>{label}{evidence?.score != null ? <b>{Math.round(evidence.score * 100)}%</b> : null}</span><input type={type} value={fields[key] ?? ''} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} />{evidence?.source_text ? <small title={evidence.source_text}>Page {evidence.source_page ?? 1}: {evidence.source_text}</small> : null}</label> })}</div><LineItemEditor items={lineItems} onChange={setLineItems} />{[...validation.map((issue) => `${issue.field_name ?? issue.field ?? 'Invoice data'}: ${issue.message}`), ...arithmeticIssues].length ? <div className="validation-list">{[...validation.map((issue) => `${issue.field_name ?? issue.field ?? 'Invoice data'}: ${issue.message}`), ...arithmeticIssues].map((message, index) => <p key={index}><AlertTriangle size={14} /><span>{message}</span></p>)}</div> : <div className="validation-ok"><CheckCircle2 size={16} /> Arithmetic checks passed.</div>}<div className="wizard-actions">{['extracted','needs_review'].includes(document?.status ?? '') ? <button className="outline-button" disabled={reprocessMutation.isPending} onClick={() => reprocessMutation.mutate()}><RefreshCw size={15} /> Reprocess</button> : null}<button className="outline-button" disabled={saveDraftMutation.isPending} onClick={() => saveDraftMutation.mutate()}>{saveDraftMutation.isPending ? <Loader2 className="spin" size={15} /> : <FileCheck2 size={15} />} Save Draft</button><button className="primary-button" disabled={arithmeticIssues.length > 0} onClick={() => setStep(3)}><Check size={17} /> Confirm Invoice Data</button></div></div></div> : null}
        {step === 3 ? <div className="submit-step"><div className="submit-summary"><WorkIcon type="invoice_review" /><div><span>READY TO SUBMIT</span><h3>{fields.vendor_name || document?.original_filename || 'Invoice'}</h3><p>{fields.invoice_number || shortId(documentId)} · {fields.currency || '-'} {fields.total || '-'}</p></div></div><fieldset className="outcome-options"><legend>What should happen next?</legend>{[['invoice_review','Review and approve invoice'],['accounting_note','Prepare accounting note'],['invoice_export','Prepare approved invoice export'],['vendor_follow_up','Request vendor information']].map(([value,label]) => <label className={outcome === value ? 'selected' : ''} key={value}><input type="radio" name="outcome" value={value} checked={outcome === value} onChange={() => setOutcome(value)} /><span><strong>{label}</strong><small>{outcomeCopy(value)}</small></span></label>)}</fieldset><div className="wizard-actions"><button className="outline-button" onClick={() => setStep(2)}>Back</button><button className="primary-button" disabled={submitMutation.isPending} onClick={() => submitMutation.mutate()}>{submitMutation.isPending ? <Loader2 className="spin" size={17} /> : <Play size={17} />} Submit for Processing</button></div>{submitMutation.error ? <p className="wizard-error">{(submitMutation.error as Error).message}</p> : null}</div> : null}
        {step === 4 ? <div className="submission-success"><CheckCircle2 size={42} /><span>SUBMISSION RECEIVED</span><h3>Invoice document submitted successfully</h3><p>Your durable reference is <strong>{shortId(documentId)}</strong>. The workflow can now be followed from the document workspace.</p><div className="success-status"><Status value={submittedItem?.status ?? 'planning'} /><span>Current owner<strong>AI Workflow</strong></span><span>Next action<strong>Generate and review the safe plan</strong></span></div><div className="wizard-actions"><button className="outline-button" onClick={() => { setStep(0); setFile(null); setDocumentId(''); setSubmittedItem(null); setFields({}); setLineItems([]) }}><Plus size={16} /> Upload Another Invoice</button><button className="primary-button" onClick={() => submittedItem && onSubmitted(submittedItem.id)}><FileClock size={16} /> View Document Status</button></div></div> : null}
      </section>
    </main>
  )
}

function PdfPreview({ url, filename }: { url: string; filename: string }) {
  return <aside className="pdf-preview"><div><FileText size={17} /><strong>{filename || 'Invoice preview'}</strong></div>{url ? <iframe title={`Preview ${filename}`} src={url} /> : <div className="preview-empty"><FileText size={34} /><span>Select a PDF to preview it here.</span></div>}</aside>
}

function LineItemEditor({ items, onChange }: { items: LineItem[]; onChange: (items: LineItem[]) => void }) {
  const update = (index: number, key: keyof LineItem, value: string) => onChange(items.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item))
  return <section className="line-items-editor"><div><h4>Line items</h4><button className="outline-button" onClick={() => onChange([...items, { description: '', quantity: '', unit_price: '', amount: '' }])}><Plus size={14} /> Add line</button></div>{items.length ? items.map((item, index) => <div className="line-item-row" key={index}><input aria-label={`Line ${index + 1} description`} placeholder="Description" value={item.description ?? ''} onChange={(event) => update(index, 'description', event.target.value)} /><input aria-label={`Line ${index + 1} quantity`} type="number" step="any" placeholder="Qty" value={item.quantity ?? ''} onChange={(event) => update(index, 'quantity', event.target.value)} /><input aria-label={`Line ${index + 1} unit price`} type="number" step="any" placeholder="Unit price" value={item.unit_price ?? ''} onChange={(event) => update(index, 'unit_price', event.target.value)} /><input aria-label={`Line ${index + 1} amount`} type="number" step="any" placeholder="Amount" value={item.amount ?? ''} onChange={(event) => update(index, 'amount', event.target.value)} /><button className="icon-button" aria-label={`Remove line ${index + 1}`} onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}><X size={15} /></button></div>) : <p>No line items were extracted. Add them when they appear on the invoice.</p>}</section>
}

function invoiceArithmeticIssues(fields: Record<string, string>, items: LineItem[]) {
  const issues: string[] = []
  items.forEach((item, index) => {
    const quantity = Number(item.quantity)
    const unitPrice = Number(item.unit_price)
    const amount = Number(item.amount)
    if ([quantity, unitPrice, amount].every(Number.isFinite) && Math.abs(quantity * unitPrice - amount) > 0.01) issues.push(`Line ${index + 1}: quantity x unit price does not equal amount.`)
  })
  const subtotal = Number(fields.subtotal)
  const tax = Number(fields.tax)
  const total = Number(fields.total)
  if ([subtotal, tax, total].every(Number.isFinite) && Math.abs(subtotal + tax - total) > 0.01) issues.push('Invoice total must equal subtotal plus tax.')
  return issues
}

const guidedFields: Array<[string, string, string]> = [['vendor_name','Vendor','text'],['invoice_number','Invoice number','text'],['invoice_date','Invoice date','date'],['due_date','Due date','date'],['subtotal','Subtotal','number'],['tax','Tax','number'],['total','Total','number'],['currency','Currency','text']]

function WorkflowOrientation({ step, owner, waiting, next }: { step: string; owner: string; waiting?: string; next: string }) {
  return <aside className="orientation-panel"><div><span>Current owner</span><strong>{owner}</strong></div><div><span>Current step</span><strong>{step}</strong></div>{waiting ? <div><span>Waiting for</span><strong>{waiting}</strong></div> : null}<div className="next"><span>Next action</span><strong>{next}</strong></div></aside>
}

function StageActivity({ events, active }: { events: DocumentDetail['audit_events']; active: boolean }) {
  const stages = [{ label: 'PDF received', done: true }, { label: 'Extraction and OCR', done: !active && events.some((event) => event.event_type === 'processing_succeeded'), active }, { label: 'Validation rules', done: !active && events.some((event) => event.event_type === 'processing_succeeded') }]
  return <div className="stage-activity"><h3>{active ? 'AI workflow is processing the invoice' : 'Ready to extract invoice data'}</h3><p>Progress is shown only when supported by durable document events.</p>{stages.map((stage) => <div key={stage.label} className={stage.done ? 'done' : stage.active ? 'active' : ''}><span>{stage.done ? <Check size={15} /> : stage.active ? <Loader2 className="spin" size={15} /> : null}</span><strong>{stage.label}</strong></div>)}</div>
}

function IntakeLibrary({ view, openItem }: { view: IntakeView; openItem: (id: string) => void }) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [createdFrom, setCreatedFrom] = useState('')
  const [createdTo, setCreatedTo] = useState('')
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState('')
  const params = new URLSearchParams({ search, status: statusFilter, page: String(page), page_size: '8' })
  if (createdFrom) params.set('created_from', createdFrom)
  if (createdTo) params.set('created_to', createdTo)
  if (view === 'submissions') params.set('submitted_by', 'William Lo')
  const invoices = useQuery({
    queryKey: ['invoice-library', view, search, statusFilter, createdFrom, createdTo, page],
    queryFn: () => api<InvoiceList>(`/invoices?${params}`),
    enabled: view !== 'guide',
  })
  if (view === 'guide') return <main className="guided-page"><section className="guided-heading"><div><span>PROCESSING GUIDE</span><h2>How an invoice moves through the system</h2><p>The operator verifies source data; the AI plans bounded work; reviewers handle exceptions and approvals.</p></div></section><div className="guide-grid">{['Upload the PDF','Extract invoice data','Verify fields and warnings','Choose a business outcome','AI generates a safe plan','Reviewer approves risky execution','System records the result'].map((title,index) => <article key={title}><span>{index + 1}</span><h3>{title}</h3></article>)}</div></main>
  const resetFilters = () => {
    setSearch('')
    setStatusFilter('')
    setCreatedFrom('')
    setCreatedTo('')
    setPage(1)
  }
  return (
    <main className="section-page">
      <section className="section-heading">
        <div>
          <span className="section-eyebrow">DOCUMENT WORK</span>
          <h2>{view === 'submissions' ? 'My Documents' : 'Document Library'}</h2>
          <p>{view === 'submissions' ? 'Invoice documents submitted by William Lo, with their current owner and workflow stage.' : 'Every invoice document in this workspace, including unfinished and failed processing.'}</p>
        </div>
      </section>
      <div className="invoice-toolbar">
        <label><Search size={16} /><input value={search} placeholder="Search filename..." onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label>
        <label className="date-filter"><span>From</span><input aria-label="Submitted from" type="date" value={createdFrom} max={createdTo || undefined} onChange={(event) => { setCreatedFrom(event.target.value); setPage(1) }} /></label>
        <label className="date-filter"><span>To</span><input aria-label="Submitted to" type="date" value={createdTo} min={createdFrom || undefined} onChange={(event) => { setCreatedTo(event.target.value); setPage(1) }} /></label>
        <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1) }}>
          <option value="">All statuses</option>
          {['queued','processing','needs_review','approved','failed','cancelled','exported'].map((status) => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}
        </select>
        {(search || statusFilter || createdFrom || createdTo) ? <button className="outline-button" onClick={resetFilters}><X size={14} /> Clear</button> : null}
      </div>
      <section className="data-panel invoice-table">
        {invoices.isLoading ? <LoadingState /> : invoices.data?.items.map((doc) => (
          <button key={doc.id} onClick={() => setSelectedId(doc.id)}>
            <WorkIcon type="invoice_review" />
            <span className="invoice-primary"><strong>{doc.vendor_name || doc.original_filename}</strong><small>{doc.original_filename} · {shortId(doc.id)}</small></span>
            <span><small>Amount</small><strong>{doc.currency || '-'} {doc.total || '-'}</strong></span>
            <span><small>Submitted</small><strong>{formatDate(doc.created_at)}</strong></span>
            <span><small>Owner</small><strong>{doc.current_owner}</strong></span>
            <span><small>Stage</small><strong>{doc.current_stage}</strong></span>
            <Status value={doc.status} /><ChevronRight size={17} />
          </button>
        ))}
        {!invoices.isLoading && !invoices.data?.items.length ? <EmptyState title="No matching invoices" body="Change the filters or upload a new invoice." /> : null}
      </section>
      {invoices.data && invoices.data.total_pages > 1 ? <div className="invoice-pagination"><button className="icon-button" disabled={page === 1} onClick={() => setPage((current) => current - 1)}><ChevronLeft size={16} /></button><span>Page {page} of {invoices.data.total_pages} · {invoices.data.total} invoices</span><button className="icon-button" disabled={page === invoices.data.total_pages} onClick={() => setPage((current) => current + 1)}><ChevronRight size={16} /></button></div> : null}
      {selectedId ? <InvoiceStatusPanel documentId={selectedId} close={() => setSelectedId('')} openItem={openItem} refresh={() => invoices.refetch()} /> : null}
    </main>
  )
}

function InvoiceStatusPanel({ documentId, close, openItem, refresh }: { documentId: string; close: () => void; openItem: (id: string) => void; refresh: () => void }) {
  const workflow = useQuery({ queryKey: ['document-workflow', documentId], queryFn: () => api<DocumentWorkflow>(`/documents/${documentId}/workflow`), refetchInterval: 5000 })
  const [pdfUrl, setPdfUrl] = useState('')
  const [escalationReason, setEscalationReason] = useState('')
  useEffect(() => {
    let objectUrl = ''
    fetch(`/documents/${documentId}/content`, { credentials: 'same-origin' })
      .then((response) => {
        if (!response.ok) throw new Error('Preview unavailable')
        return response.blob()
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setPdfUrl(objectUrl)
      })
      .catch(() => setPdfUrl(''))
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [documentId])
  const refreshAll = () => { workflow.refetch(); refresh() }
  const retry = useMutation({ mutationFn: () => api(`/documents/${documentId}/retry`, { method: 'POST' }), onSuccess: refreshAll })
  const reprocess = useMutation({ mutationFn: () => api(`/documents/${documentId}/reprocess`, { method: 'POST' }), onSuccess: refreshAll })
  const cancel = useMutation({ mutationFn: () => api(`/documents/${documentId}/cancel`, { method: 'POST' }), onSuccess: refreshAll })
  const escalate = useMutation({
    mutationFn: () => api(`/documents/${documentId}/escalate`, { method: 'POST', body: JSON.stringify({ reason: escalationReason.trim() }) }),
    onSuccess: () => { setEscalationReason(''); refreshAll() },
  })
  const data = workflow.data
  const mutationError = retry.error || reprocess.error || cancel.error || escalate.error
  return (
    <div className="invoice-detail-overlay">
      <button className="invoice-detail-scrim" aria-label="Close invoice status" onClick={close} />
      <aside className="invoice-status-panel">
        <header><div><span>INVOICE STATUS</span><h2>{data?.document.original_filename ?? 'Loading invoice...'}</h2></div><button className="icon-button" aria-label="Close" onClick={close}><X size={18} /></button></header>
        {workflow.isLoading ? <LoadingState /> : data ? <>
          <div className="status-orientation"><div><small>Stage</small><strong>{data.current_stage}</strong></div><div><small>Owner</small><strong>{data.current_owner}</strong></div><div><small>Next action</small><strong>{data.next_action}</strong></div><Status value={data.document.status} /></div>
          <PdfPreview url={pdfUrl} filename={data.document.original_filename} />
          <section className="status-extraction"><h3>Extracted invoice</h3><div>{guidedFields.map(([key, label]) => <span key={key}><small>{label}</small><strong>{String(data.extraction?.data?.[key] ?? '-')}</strong></span>)}</div></section>
          {data.extraction?.validation?.length ? <div className="validation-list">{data.extraction.validation.map((issue, index) => <p key={index}><AlertTriangle size={14} /><span>{issue.field_name ?? issue.field}: {issue.message}</span></p>)}</div> : null}
          {data.attention_reason ? <div className="duplicate-warning"><AlertTriangle size={16} /><span><strong>Attention required</strong>{data.attention_reason}</span></div> : null}
          <section className="status-activity"><h3>Recent activity</h3>{data.activity.slice(-5).reverse().map((event) => <div key={event.id}><span /><p><strong>{event.summary}</strong><small>{event.actor} · {formatDate(event.created_at)}</small></p></div>)}</section>
          {data.work_item ? <section className="escalation-control"><label>Escalation reason<textarea value={escalationReason} placeholder="Explain why a senior operator is needed..." onChange={(event) => setEscalationReason(event.target.value)} /></label><button className="outline-button" disabled={!escalationReason.trim() || escalate.isPending} onClick={() => escalate.mutate()}><AlertTriangle size={15} /> Escalate</button></section> : null}
          {mutationError ? <p className="wizard-error">{(mutationError as Error).message}</p> : null}
          <footer>
            {pdfUrl ? <a className="outline-button" href={pdfUrl} download={data.document.original_filename}><FileText size={15} /> Download PDF</a> : null}
            {data.document.status === 'failed' ? <button className="outline-button" disabled={retry.isPending} onClick={() => retry.mutate()}><RefreshCw size={15} /> Retry Processing</button> : null}
            {['extracted','needs_review','cancelled'].includes(data.document.status) ? <button className="outline-button" disabled={reprocess.isPending} onClick={() => reprocess.mutate()}><RefreshCw size={15} /> Reprocess</button> : null}
            {['queued','failed'].includes(data.document.status) ? <button className="danger-outline-button" disabled={cancel.isPending} onClick={() => cancel.mutate()}><X size={15} /> Cancel Intake</button> : null}
            {data.work_item ? <button className="primary-button" onClick={() => openItem(data.work_item!.id)}><FileClock size={15} /> Open Workflow Status</button> : null}
          </footer>
        </> : <ErrorState message={(workflow.error as Error)?.message ?? 'Invoice unavailable'} retry={() => workflow.refetch()} />}
      </aside>
    </div>
  )
}

function OperationsOverview({ workspace, loading, openItem, goQueue }: { workspace?: Workspace; loading: boolean; openItem: (id: string) => void; goQueue: (filter?: QueueFilter) => void }) {
  const [createOpen, setCreateOpen] = useState(false)
  const providerHealth = useQuery({ queryKey: ['provider-health'], queryFn: () => api<ProviderHealth>('/providers/health'), refetchInterval: 15000 })
  const workerHealth = useQuery({ queryKey: ['operations-jobs'], queryFn: () => api<OperationsJobs>('/operations/jobs'), refetchInterval: 15000 })
  const items = workspace?.work_items ?? []
  const attention = items.filter((item) => ['awaiting_human','blocked','failed'].includes(item.status))
  const counts = queueCounts(items)
  const failedDocuments = workspace?.documents.filter((document) => document.status === 'failed').length ?? 0
  const executing = items.filter((item) => item.status === 'executing').length
  const completedToday = items.filter((item) => item.status === 'resolved' && isToday(item.updated_at)).length
  const metrics: Array<[string, number | string, React.ReactNode, QueueFilter | undefined]> = [
    ['Needs attention', attention.length, <AlertTriangle key="attention" size={18} />, 'attention'],
    ['Waiting approval', counts.approval, <UserRound key="approval" size={18} />, 'approval'],
    ['Executing', executing, <Play key="executing" size={18} />, 'progress'],
    ['Completed today', completedToday, <CheckCircle2 key="completed" size={18} />, 'completed'],
    ['Failed processing', failedDocuments, <FileClock key="failed" size={18} />, 'blocked'],
    ['Provider health', humanize(providerHealth.data?.overall_status ?? 'checking'), <ShieldCheck key="health" size={18} />, undefined],
    ['Worker health', humanize(workerHealth.data?.worker.status ?? 'checking'), <CircleGauge key="worker" size={18} />, undefined],
  ]
  return <main className="section-page"><section className="section-heading"><div><span className="section-eyebrow">ADMINISTRATOR / REVIEWER</span><h2>Work Summary</h2><p>Document attention, approvals, failures, and completed work in one place.</p></div><div className="section-actions"><button className="outline-button" onClick={() => setCreateOpen(true)}><Plus size={15} /> New Document Task</button><button className="primary-button" onClick={() => goQueue('attention')}>Open Work Queue</button></div></section><div className="overview-metrics">{metrics.map(([label,value,icon,filter]) => <button key={label} disabled={!filter} onClick={() => filter && goQueue(filter)}><span>{icon}</span><small>{label}</small><strong>{loading ? '-' : value}</strong><ChevronRight size={15} /></button>)}</div><section className="provider-health-strip"><header><ShieldCheck size={17} /><strong>Provider Health</strong><Status value={providerHealth.data?.overall_status ?? 'checking'} /></header>{providerHealth.data?.providers.map((provider) => <article key={provider.role}><div><small>{humanize(provider.role)}</small><strong>{provider.provider_name}</strong></div><Status value={provider.status} /><span>{provider.observed_runs} runs · {provider.observed_failures} failures</span><p>{provider.evidence}</p></article>)}</section><section className="data-panel"><DataPanelHeader icon={<Inbox size={17} />} title="Needs Human Attention" count={attention.length} />{loading ? <LoadingState /> : attention.length ? <div className="overview-attention">{attention.map((item) => <button key={item.id} onClick={() => openItem(item.id)}><WorkIcon type={item.work_type} /><span><strong>{item.title}</strong><small>{attentionReason(item)} Decision: {decisionRequired(item)}</small></span><Status value={item.status} /><ChevronRight size={16} /></button>)}</div> : <div className="healthy-empty"><CheckCircle2 size={28} /><div><strong>No documents require attention</strong><p>Active processing is continuing normally.</p></div></div>}</section>{createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}</main>
}

function QueuePage({ workspace, loading, openItem, attentionOnly = false, exceptionMode = false, initialFilter }: { workspace?: Workspace; loading: boolean; openItem: (id: string) => void; attentionOnly?: boolean; exceptionMode?: boolean; initialFilter?: QueueFilter }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<QueueFilter>(initialFilter ?? 'all')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [exceptionFilter, setExceptionFilter] = useState<ExceptionFilter>('all')
  const [showFilters, setShowFilters] = useState(false)
  const [showColumns, setShowColumns] = useState(false)
  const [visibleColumns, setVisibleColumns] = useState({ assignee: true, updated: true })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(1)
  const pageSize = 8
  const [createOpen, setCreateOpen] = useState(false)
  useEffect(() => { if (initialFilter) setFilter(initialFilter) }, [initialFilter])
  const allItems = workspace?.work_items ?? []
  const exceptionItems = allItems.filter((item) => ['awaiting_human', 'blocked', 'failed'].includes(item.status) || ['vendor_follow_up', 'insufficient_evidence'].includes(item.work_type ?? '') || item.linked_document_ids.some((id) => workspace?.documents.find((document) => document.id === id)?.status === 'needs_review'))
  const items = attentionOnly || exceptionMode ? exceptionItems : allItems
  const counts = queueCounts(items)
  const filtered = items.filter((item) => matchesFilter(item, filter) && (!attentionOnly || matchesExceptionFilter(item, exceptionFilter, workspace?.documents ?? [])) && (!priorityFilter || item.priority === priorityFilter) && `${item.title} ${item.id} ${item.assignee}`.toLowerCase().includes(search.toLowerCase()))
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize)
  useEffect(() => { setPage(1) }, [search, filter, priorityFilter, exceptionFilter])
  useEffect(() => { if (page > totalPages) setPage(totalPages) }, [page, totalPages])
  const bulkPriority = useMutation({
    mutationFn: () => Promise.all([...selected].map((id) => api(`/backoffice/work-items/${id}`, { method: 'PATCH', body: JSON.stringify({ priority: 'high' }) }))),
    onSuccess: () => { setSelected(new Set()); queryClient.invalidateQueries({ queryKey: ['workspace'] }) },
  })

  const metrics = [
    ['Document Tasks', items.length, Inbox, 'blue', 'All active records'],
    ['Needs Attention', counts.attention, AlertTriangle, 'red', 'High priority or blocked'],
    ['In Progress', counts.progress, Play, 'blue', 'Currently planned'],
    ['Waiting Approval', counts.approval, UserRound, 'amber', 'Pending human review'],
    ['Completed Today', counts.completed, ShieldCheck, 'green', 'Resolved work items'],
  ] as const

  return (
    <main className="queue-page">
      <section className="page-heading">
        <div><h2>{exceptionMode ? 'Exception Queue' : 'Work Queue'}</h2><p>{exceptionMode ? 'Only documents that require human review, correction, approval, or recovery.' : 'All incoming and in-progress document operations, organized by risk and next action.'}</p></div>
        <div className="queue-tools">
          <label className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search document tasks..." /><kbd>⌘ K</kbd></label>
          <button className={`outline-button ${showFilters ? 'active' : ''}`} onClick={() => setShowFilters((value) => !value)}><Filter size={15} /> Filters</button>
          <button className={`outline-button ${showColumns ? 'active' : ''}`} onClick={() => setShowColumns((value) => !value)}><Columns3 size={15} /> Columns</button>
          <button className="primary-button" onClick={() => setCreateOpen(true)}><Plus size={16} /> New Document Task</button>
        </div>
      </section>
      {showFilters ? <section className="queue-control-panel"><label>Priority<select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}><option value="">All priorities</option>{['low','normal','high','urgent'].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><button className="outline-button" onClick={() => { setPriorityFilter(''); setSearch(''); setFilter('all') }}><X size={14} /> Reset filters</button></section> : null}
      {showColumns ? <section className="queue-control-panel"><label><input type="checkbox" checked={visibleColumns.assignee} onChange={(event) => setVisibleColumns((current) => ({ ...current, assignee: event.target.checked }))} /> Assignee</label><label><input type="checkbox" checked={visibleColumns.updated} onChange={(event) => setVisibleColumns((current) => ({ ...current, updated: event.target.checked }))} /> Updated</label></section> : null}
      {selected.size ? <section className="bulk-bar"><strong>{selected.size} selected</strong><button className="outline-button" disabled={bulkPriority.isPending} onClick={() => bulkPriority.mutate()}><AlertTriangle size={14} /> Set High Priority</button><button className="outline-button" onClick={() => setSelected(new Set())}><X size={14} /> Clear</button></section> : null}
      <section className="metric-row">
        {metrics.map(([label, value, Icon, tone, note]) => (
          <article className="metric-card" key={label}>
            <span className={`metric-icon ${tone}`}><Icon size={20} /></span>
            <div><p>{label}</p><strong>{loading ? '-' : value}</strong><small>{note}</small></div>
          </article>
        ))}
      </section>
      <section className="queue-surface">
        {exceptionMode || attentionOnly ? <div className="exception-tabs">{([['all','All Exceptions'],['missing_information','Missing Information'],['validation_failure','Validation Failure'],['waiting_approval','Waiting Approval'],['blocked','Blocked'],['failed','Failed']] as [ExceptionFilter,string][]).map(([value,label]) => <button className={exceptionFilter === value ? 'active' : ''} key={value} onClick={() => setExceptionFilter(value)}>{label} <span>{items.filter((item) => matchesExceptionFilter(item, value, workspace?.documents ?? [])).length}</span></button>)}</div> : null}
        <div className="queue-tabs">
          {([
            ['all', `All (${items.length})`],
            ['attention', `Needs Attention (${counts.attention})`],
            ['progress', `In Progress (${counts.progress})`],
            ['approval', `Waiting Approval (${counts.approval})`],
            ['completed', `Completed (${counts.completed})`],
            ['blocked', `Blocked (${counts.blocked})`],
          ] as [QueueFilter, string][]).map(([value, label]) => <button className={filter === value ? 'active' : ''} onClick={() => setFilter(value)} key={value}>{label}</button>)}
        </div>
        <WorkItemTable items={paged} documents={workspace?.documents ?? []} loading={loading} openItem={openItem} selected={selected} setSelected={setSelected} visibleColumns={visibleColumns} page={page} totalPages={totalPages} total={filtered.length} setPage={setPage} />
      </section>
      {createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}
    </main>
  )
}

function WorkItemTable({ items, documents, loading, openItem, selected, setSelected, visibleColumns, page, totalPages, total, setPage }: { items: WorkItemSummary[]; documents: DocumentSummary[]; loading: boolean; openItem: (id: string) => void; selected: Set<string>; setSelected: (value: Set<string>) => void; visibleColumns: { assignee: boolean; updated: boolean }; page: number; totalPages: number; total: number; setPage: (page: number) => void }) {
  if (loading) return <LoadingState />
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.id))
  const toggleAll = () => {
    const next = new Set(selected)
    if (allSelected) items.forEach((item) => next.delete(item.id)); else items.forEach((item) => next.add(item.id))
    setSelected(next)
  }
  return (
    <div className="table-wrap">
      <table className="work-table">
        <thead><tr><th><input type="checkbox" aria-label="Select all on page" checked={allSelected} onChange={toggleAll} /></th><th>Document</th><th>Vendor / Amount</th><th>Type</th><th>Status</th><th>Risk / Attention</th>{visibleColumns.assignee ? <th>Owner</th> : null}{visibleColumns.updated ? <th>Updated</th> : null}<th>Next Action</th><th /></tr></thead>
        <tbody>
          {items.map((item) => {
            const document = linkedDocumentForItem(item, documents)
            return (
              <tr key={item.id} onClick={() => openItem(item.id)}>
                <td onClick={(e) => e.stopPropagation()}><input type="checkbox" aria-label={`Select ${item.title}`} checked={selected.has(item.id)} onChange={() => { const next = new Set(selected); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); setSelected(next) }} /></td>
                <td><div className="item-cell"><WorkIcon type={item.work_type} /><div><strong>{document?.filename ?? item.title}</strong><small>{item.title}</small><span>{businessId(item)} · {item.linked_document_ids.length ? `${item.linked_document_ids.length} linked` : 'Manual intake'}</span></div></div></td>
                <td><div className="vendor-cell"><strong>{queueVendor(item, document)}</strong><span>{queueAmount(item)}</span></div></td>
                <td><TypeBadge value={queueDocumentType(item)} /></td>
                <td><Status value={item.status} /></td>
                <td><div className="attention-cell"><Priority value={item.priority} /><span>{attentionReason(item)}</span></div></td>
                {visibleColumns.assignee ? <td><div className="assignee"><span className="mini-avatar">{item.assignee === 'Unassigned' ? '?' : item.assignee.slice(0,1)}</span>{item.assignee}</div></td> : null}
                {visibleColumns.updated ? <td>{formatDate(item.updated_at)}</td> : null}
                <td><button className="row-action" onClick={(event) => { event.stopPropagation(); openItem(item.id) }}>{nextAction(item.status)}</button></td>
                <td><button className="icon-button" aria-label={`Open ${item.title}`} onClick={(event) => { event.stopPropagation(); openItem(item.id) }}><MoreHorizontal size={17} /></button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {items.length === 0 ? <EmptyState title="No matching document tasks" body="Try another search or queue filter." /> : null}
      <div className="pagination"><span>Showing {items.length} of {total} items</span><div><button aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={15} /></button><button className="active" aria-current="page" disabled>{page}</button><button aria-label="Next page" disabled={page >= totalPages} onClick={() => setPage(page + 1)}><ChevronRight size={15} /></button></div><button disabled>{page} / {totalPages} pages</button></div>
    </div>
  )
}

function WorkItemPage({
  itemId,
  workspace,
  loadingWorkspace,
  openItem,
}: {
  itemId: string
  workspace?: Workspace
  loadingWorkspace: boolean
  openItem: (id: string) => void
}) {
  const detail = useQuery({
    queryKey: ['work-item', itemId],
    queryFn: () => api<{ work_item: WorkItemDetail }>(`/backoffice/work-items/${itemId}`).then((data) => data.work_item),
  })
  const item = detail.data
  const items = workspace?.work_items ?? []
  const currentIndex = items.findIndex((entry) => entry.id === itemId)
  const linkedDocument = workspace?.documents.find((doc) => item?.linked_document_ids.includes(doc.id))
  const documentDetail = useQuery({
    queryKey: ['document-detail', linkedDocument?.id],
    queryFn: () => api<DocumentDetail>(`/documents/${linkedDocument?.id}`),
    enabled: Boolean(linkedDocument),
  })
  const documentWorkflow = useQuery({
    queryKey: ['document-workflow', linkedDocument?.id],
    queryFn: () => api<DocumentWorkflow>(`/documents/${linkedDocument?.id}/workflow`),
    enabled: Boolean(linkedDocument),
    refetchInterval: 5000,
  })
  const [activeTab, setActiveTab] = useState('Review')
  const [editOpen, setEditOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)

  if (detail.error) return <ErrorState message={(detail.error as Error).message} retry={() => detail.refetch()} />
  if (!item || loadingWorkspace) return <LoadingState />

  const tabs = ['Review', 'Next Steps', 'Approval Decision', 'Record', 'Safety Rules', 'History', 'Technical Evidence']

  return (
    <main className="detail-page">
      <aside className="inbox-rail">
        <div className="rail-title"><h2>Work Queue</h2><button className="primary-button" onClick={() => setCreateOpen(true)}><Plus size={15} /> New Document Task</button></div>
        <div className="rail-filter"><span>All ({items.length})</span><ChevronDown size={14} /><button aria-label="Filter inbox" title="Inbox filters are not available yet" disabled><Filter size={15} /></button><button aria-label="Inbox view options" title="View options are not available yet" disabled><Columns3 size={15} /></button></div>
        <div className="rail-items">
          {items.map((entry) => <InboxCard key={entry.id} item={entry} active={entry.id === item.id} open={() => openItem(entry.id)} />)}
        </div>
        <div className="rail-footer">Showing {items.length} of {items.length}<RefreshCw size={14} /></div>
      </aside>
      <section className="work-detail">
        <header className="detail-header">
          <div className="detail-heading">
            <TypeBadge value={item.work_type} />
            <h2>{item.title} <button className="inline-edit" aria-label="Edit work item" onClick={() => setEditOpen(true)}><Pencil size={14} /></button></h2>
          </div>
          <div className="detail-header-actions">
            <button className="outline-button" onClick={() => setEditOpen(true)}><Pencil size={16} /> Edit Document Task</button>
            <div className="pager">
              <button disabled={currentIndex <= 0} onClick={() => openItem(items[currentIndex - 1]?.id)}><ChevronLeft size={17} /></button>
              <button disabled={currentIndex < 0 || currentIndex >= items.length - 1} onClick={() => openItem(items[currentIndex + 1]?.id)}><ChevronRight size={17} /></button>
            </div>
          </div>
          <div className="detail-meta">
            <Meta label="ID" value={businessId(item)} />
            <Meta label="Received" value={formatDate(item.created_at)} />
            <Meta label="Source" value={linkedDocument?.filename ?? 'Manual intake'} icon={<FileText size={14} />} />
            <Meta label="Priority" value={<Priority value={item.priority} />} />
            <Meta label="Status" value={<Status value={item.status} />} />
          </div>
          <DetailDecisionSummary item={item} document={linkedDocument} />
        </header>
        <div className="detail-tabs">
          {tabs.map((tab) => (
            <button className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)} key={tab}>{tab}</button>
          ))}
        </div>
        {activeTab === 'Review' ? (
          <WorkspaceTab item={item} document={linkedDocument} documentDetail={documentDetail.data?.document} extraction={documentDetail.data?.extraction ?? null} loading={documentDetail.isLoading} />
        ) : activeTab === 'Next Steps' ? (
          <PlanTab item={item} />
        ) : activeTab === 'Record' ? (
          <RecordTab item={item} documents={workspace?.documents.filter((document) => item.linked_document_ids.includes(document.id)) ?? []} document={linkedDocument} documentDetail={documentDetail.data?.document} extraction={documentDetail.data?.extraction ?? null} loading={documentDetail.isLoading} />
        ) : activeTab === 'Safety Rules' ? (
          <GovernanceTab item={item} />
        ) : activeTab === 'Approval Decision' ? <ApprovalTab item={item} document={linkedDocument} extraction={documentDetail.data?.extraction ?? null} /> :
            activeTab === 'History' ? <ActivityTab workflow={documentWorkflow.data} documentId={linkedDocument?.id} loading={documentWorkflow.isLoading} error={documentWorkflow.error as Error | null} /> :
              activeTab === 'Technical Evidence' ? <AgentOpsTab item={item} /> :
                <EmptyState title={`${activeTab} timeline`} body="This view is not available for the current workflow." />}
      </section>
      {editOpen ? <EditWorkItemModal item={item} close={() => setEditOpen(false)} /> : null}
      {createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}
    </main>
  )
}

function DetailDecisionSummary({ item, document }: { item: WorkItemDetail; document?: DocumentSummary }) {
  const nextStep = item.current_plan?.steps.find((step) => !['completed', 'executed'].includes(step.status)) ?? item.current_plan?.steps[0]
  const pendingApproval = item.approvals.find((approval) => approval.status === 'pending')
  return (
    <section className="decision-summary" aria-label="Work item decision summary">
      <article>
        <span>Current state</span>
        <strong>{attentionReason(item)}</strong>
        <p>{decisionRequired(item)}</p>
      </article>
      <article>
        <span>Next step</span>
        <strong>{nextStep ? humanize(nextStep.action_type) : item.current_plan ? 'Plan has no open step' : 'Generate or review a plan'}</strong>
        <p>{nextStep?.why_this ?? item.requested_outcome ?? 'Confirm the available evidence before taking action.'}</p>
      </article>
      <article>
        <span>Decision needed</span>
        <strong>{pendingApproval ? 'Approval decision pending' : item.current_plan?.requires_human ? 'Human review required' : 'No approval gate open'}</strong>
        <p>{pendingApproval ? 'Open Approval Decision to approve or reject the controlled action.' : item.current_plan?.requires_human ? 'Review the plan and evidence before execution.' : 'Continue from the next available workflow step.'}</p>
      </article>
      <article>
        <span>Source evidence</span>
        <strong>{document?.filename ?? 'No linked source'}</strong>
        <p>{document ? `Document status: ${humanize(document.status)}.` : 'Link a source document before making a final decision.'}</p>
      </article>
    </section>
  )
}

function InboxCard({ item, active, open }: { item: WorkItemSummary; active: boolean; open: () => void }) {
  return (
    <button className={`inbox-card ${active ? 'active' : ''}`} onClick={open}>
      <div><Priority value={item.priority} /><small>{humanize(item.work_type ?? 'unclassified')}</small></div>
      <strong>{item.title}</strong>
      <p>{businessId(item)} <i /> {relativeTime(item.updated_at)}</p>
      <Status value={item.status} />
      <span className="mini-avatar">W</span>
    </button>
  )
}

function WorkspaceTab({ item, document, documentDetail, extraction, loading }: { item: WorkItemDetail; document?: DocumentSummary; documentDetail?: ApiDocument; extraction: Extraction | null; loading: boolean }) {
  const fields = invoiceFields(extraction)
  const issues = extraction?.validation ?? []
  const evidence = extraction?.confidence ?? []
  const lineItems = invoiceLineItems(extraction)
  const nextStep = item.current_plan?.steps.find((step) => !['completed', 'executed'].includes(step.status)) ?? item.current_plan?.steps[0]
  const recentActivity = item.activity.slice(-4).reverse()

  return (
    <div className="document-workspace">
      <section className={`workspace-alert ${issues.length ? 'has-issues' : evidence.length ? 'clear' : 'missing'}`}>
        {issues.length ? <AlertTriangle size={18} /> : evidence.length ? <CheckCircle2 size={18} /> : <FileClock size={18} />}
        <div><strong>{issues.length ? `${issues.length} validation issue${issues.length === 1 ? ' requires' : 's require'} review` : evidence.length ? 'Extraction evidence is available' : 'Extraction evidence is not available'}</strong><p>{issues.length ? 'Resolve deterministic validation findings before relying on the proposed action.' : evidence.length ? `${evidence.length} extracted fields include stored confidence or source evidence.` : 'No stored field-level confidence or source excerpts were returned for this document.'}</p></div>
        <Priority value={item.priority} />
      </section>

      <div className="workspace-primary">
        <section className="workspace-preview">
          <div className="workspace-section-heading"><div><span>Source document</span><h3>{document?.filename ?? 'No linked document'}</h3></div>{document ? <Status value={document.status} /> : null}</div>
          {loading ? <LoadingState /> : document ? <AuthenticatedPdfPreview document={document} /> : <EmptyState title="No source preview" body="Link a document before reviewing extraction evidence." />}
        </section>

        <div className="workspace-review">
          <section className="panel workspace-fields">
            <PanelTitle title="Extracted Invoice Fields" action={<TypeBadge value="invoice" />} />
            <p className="workspace-context">Current extraction schema is invoice-specific. Unavailable values remain visibly unverified.</p>
            <SchemaMeta document={documentDetail} extraction={extraction} />
            <div className="invoice-fields">{fields.map(([label, value]) => <div className={value === '-' ? 'field-missing' : ''} key={label}><span>{label}</span><strong>{value}</strong><small><i /> {value === '-' ? 'Missing evidence' : 'Stored extraction'}</small></div>)}</div>
          </section>

          <section className="panel workspace-validation">
            <PanelTitle title="Validation" action={<span className={`severity-badge severity-${issues.length ? validationSeverity(issues) : 'clear'}`}>{issues.length ? humanize(validationSeverity(issues)) : 'Passed'}</span>} />
            {issues.length ? <div className="validation-issues">{issues.map((issue, index) => <article key={`${issue.field_name ?? issue.field}-${index}`}><AlertTriangle size={15} /><div><strong>{humanize(issue.field_name ?? issue.field ?? 'Document data')}</strong><p>{issue.message ?? 'Validation issue requires review.'}</p></div><span className={`severity-badge severity-${issue.severity ?? 'warning'}`}>{humanize(issue.severity ?? 'warning')}</span></article>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No validation blockers were returned.</div>}
          </section>

          <section className="panel workspace-line-items">
            <PanelTitle title="Invoice Line Items" action={<span className="version">{lineItems.length} items</span>} />
            {lineItems.length ? <div className="line-items-table"><div><strong>Description</strong><strong>Qty</strong><strong>Unit price</strong><strong>Amount</strong></div>{lineItems.map((line, index) => <div key={index}><span>{line.description || '-'}</span><span>{line.quantity || '-'}</span><span>{line.unit_price || '-'}</span><strong>{line.amount || '-'}</strong></div>)}</div> : <EmptyState title="No line items stored" body="The current extraction did not return invoice line-item data." />}
          </section>

          <section className="panel workspace-evidence">
            <PanelTitle title="Evidence & Source Excerpts" action={<span className="version">{evidence.length} fields</span>} />
            {evidence.length ? <div className="evidence-list">{evidence.map((entry) => <article className={!entry.source_text ? 'evidence-missing' : ''} key={entry.field_name}><strong>{humanize(entry.field_name)}</strong><EvidenceConfidence score={entry.score} /><p>{entry.source_text || 'No source excerpt stored for this field.'}</p><small>{entry.source_page ? `Source page ${entry.source_page}` : 'Source page not recorded'}</small></article>)}</div> : <div className="missing-evidence"><AlertTriangle size={17} /><div><strong>No field-level evidence</strong><p>The backend returned no confidence records or source excerpts. Values above must be checked against the PDF.</p></div></div>}
          </section>
        </div>
      </div>

      <div className="workspace-secondary">
        <section className="panel proposed-action">
          <PanelTitle title="Proposed Action" action={item.current_plan ? <Confidence value={item.current_plan.overall_confidence} /> : undefined} />
          {nextStep ? <div className="proposed-action-body"><span className="work-icon purple"><Workflow size={17} /></span><div><strong>{humanize(nextStep.action_type)}</strong><p>{nextStep.why_this || 'This bounded workflow action is the next available plan step.'}</p><div><Priority value={nextStep.risk_level} /><Status value={nextStep.status} />{nextStep.requires_approval ? <span className="severity-badge severity-warning">Approval required</span> : null}</div></div></div> : <EmptyState title="No proposed action" body="Generate a plan after the document evidence has been reviewed." />}
        </section>
        <section className="panel workspace-activity">
          <PanelTitle title="Recent Workflow Activity" action={<span className="version">{item.activity.length} events</span>} />
          {recentActivity.length ? <div className="activity-list">{recentActivity.map((event) => <article key={event.id}><span className={`activity-dot source-${event.source}`}><Check size={13} /></span><div><strong>{humanize(event.event_type)}</strong><p>{event.summary}</p><small>{event.actor} · {formatDate(event.created_at)}</small></div></article>)}</div> : <EmptyState title="No activity recorded" body="Workflow events will appear after processing begins." />}
        </section>
      </div>
    </div>
  )
}

function PlanTab({ item }: { item: WorkItemDetail }) {
  return (
    <div className="plan-tab-page">
      <PlanTimeline item={item} />
      <div className="plan-support-column">
        <TraceCard item={item} />
        <DraftPreview drafts={item.drafts} />
      </div>
    </div>
  )
}

function DetailsTab({ item, documents }: { item: WorkItemDetail; documents: DocumentSummary[] }) {
  return (
    <div className="work-item-subpage">
      <section className="panel detail-overview">
        <PanelTitle title="Document Task Details" />
        <div className="detail-definition-grid">
          <DetailField label="Business ID" value={businessId(item)} />
          <DetailField label="Work type" value={humanize(item.work_type ?? 'unclassified')} />
          <DetailField label="Priority" value={<Priority value={item.priority} />} />
          <DetailField label="Status" value={<Status value={item.status} />} />
          <DetailField label="Assignee" value={<span className="assignee"><span className="mini-avatar">{item.assignee.slice(0,1)}</span> {item.assignee}</span>} />
          <DetailField label="Source" value={documents[0]?.filename ?? 'Manual intake'} />
          <DetailField label="Created" value={formatDate(item.created_at)} />
          <DetailField label="Last updated" value={formatDate(item.updated_at)} />
        </div>
      </section>
      <section className="panel outcome-panel">
        <PanelTitle title="Requested Outcome" />
        <p>{item.requested_outcome || 'No requested outcome was provided.'}</p>
      </section>
      <TagsPanel item={item} />
      <section className="panel linked-records">
        <PanelTitle title="Linked Documents" action={<span className="version">{documents.length} records</span>} />
        {documents.length ? documents.map((document) => <div key={document.id}><WorkIcon type="invoice_review" /><span><strong>{document.filename}</strong><small>{shortId(document.id)} · {formatDate(document.created_at)}</small><SchemaMeta document={document} extraction={null} compact /></span><Status value={document.status} /></div>) : <EmptyState title="No linked documents" body="This work item was created without source evidence." />}
      </section>
    </div>
  )
}

function RecordTab({ item, documents, document, documentDetail, extraction, loading }: { item: WorkItemDetail; documents: DocumentSummary[]; document?: DocumentSummary; documentDetail?: ApiDocument; extraction: Extraction | null; loading: boolean }) {
  return (
    <div className="record-tab-page">
      <DetailsTab item={item} documents={documents} />
      <DocumentTab document={document} documentDetail={documentDetail} extraction={extraction} loading={loading} />
      <DraftTab item={item} />
    </div>
  )
}

function GovernanceTab({ item }: { item: WorkItemDetail }) {
  const latest = item.policy_decisions.at(-1)
  return (
    <div className="work-item-subpage governance-subpage">
      <section className="panel governance-summary">
        <PanelTitle title="Risk & Policy" />
        <div className="detail-definition-grid">
          <DetailField label="Autonomy level" value={latest ? humanize(latest.autonomy_level) : 'Balanced'} />
          <DetailField label="Current risk" value={<Priority value={latest?.risk_level ?? item.priority} />} />
          <DetailField label="Human confirmation" value={item.current_plan?.requires_human ? 'Required' : 'Not required'} />
          <DetailField label="Observed decisions" value={item.policy_decisions.length} />
        </div>
      </section>
      <section className="panel governance-explanation">
        <PanelTitle title="Governance Boundary" />
        <div className="notice success"><ShieldCheck size={18} /><div><strong>Bounded autonomy is active</strong><p>Execution is constrained by tool risk, workspace scope, evidence state, and explicit approval requirements.</p></div></div>
      </section>
      <section className="panel decision-log">
        <PanelTitle title="Policy Decision Log" action={<span className="version">{item.policy_decisions.length} decisions</span>} />
        {item.policy_decisions.length ? item.policy_decisions.map((decision) => <article key={decision.id}><span className={`policy-result ${decision.allowed ? 'allowed' : 'blocked'}`}>{decision.allowed ? <Check size={15} /> : <X size={15} />}</span><div><strong>{humanize(decision.action_type)}</strong><p>{decision.reason}</p></div><div><Priority value={decision.risk_level} /><Status value={decision.requires_confirmation ? 'awaiting_human' : decision.allowed ? 'approved' : 'blocked'} /></div></article>) : <EmptyState title="No policy decisions" body="Generate a plan to evaluate its actions against document execution policy." />}
      </section>
    </div>
  )
}

function PlanTimeline({ item }: { item: WorkItemDetail }) {
  const queryClient = useQueryClient()
  const planMutation = useMutation({
    mutationFn: () => api(`/backoffice/work-items/${item.id}/plan`, {
      method: 'POST',
      body: JSON.stringify({ requested_outcome: item.business_context.requested_outcome ?? '' }),
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); queryClient.invalidateQueries({ queryKey: ['work-item', item.id] }) },
  })
  const executeMutation = useMutation({
    mutationFn: (stepId: string) => api(`/backoffice/work-items/${item.id}/steps/${stepId}/execute`, { method: 'POST' }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); queryClient.invalidateQueries({ queryKey: ['work-item', item.id] }) },
  })
  const approvalByStep = new Map(item.approvals.filter((a) => a.action_step_id).map((a) => [a.action_step_id, a]))
  const steps = item.current_plan?.steps ?? []

  return (
    <section className="panel plan-panel">
      <PanelTitle title="Proposed Plan" action={<button className="small-button" onClick={() => planMutation.mutate()} disabled={planMutation.isPending}>{planMutation.isPending ? <Loader2 className="spin" size={14} /> : <Pencil size={13} />} {steps.length ? 'Regenerate' : 'Generate Plan'}</button>} />
      {steps.length ? <div className="plan-timeline">
        {steps.map((step, index) => {
          const approval = approvalByStep.get(step.id)
          const canExecute = !step.requires_approval || approval?.status === 'approved'
          return <div className={`timeline-step ${step.status}`} key={step.id}>
            <span className="step-number">{index + 1}</span>
            <div><strong>{humanize(step.action_type)}</strong><p>{step.why_this ?? 'Controlled workflow action'}</p></div>
            <div className="step-state"><Status value={step.status} />{step.status !== 'executed' && step.status !== 'blocked' ? <button title={canExecute ? 'Execute approved step' : 'Human approval is required before execution'} disabled={!canExecute || executeMutation.isPending} onClick={() => executeMutation.mutate(step.id)}><Play size={13} /></button> : null}</div>
          </div>
        })}
      </div> : <EmptyState title="No plan generated" body="Generate a safe action plan for this work item." />}
    </section>
  )
}

function TagsPanel({ item }: { item: WorkItemDetail }) {
  return <section className="panel compact-panel"><PanelTitle title="Tags" /><div className="tag-list">{item.tags.length ? item.tags.map((tag) => <span key={tag}>{tag}</span>) : <span>no-tags</span>}</div></section>
}

function DraftPreview({ drafts }: { drafts: Draft[] }) {
  const draft = drafts.at(-1)
  return <section className="panel draft-card"><PanelTitle title="AI Draft" action={draft ? <span className="version">Version {drafts.length}</span> : undefined} />{draft ? <><pre>{draft.preview_content}</pre><small>{drafts.length} saved version(s). Open Drafts to edit or regenerate.</small></> : <EmptyState title="No draft yet" body="Generate a plan that includes a drafting action." />}</section>
}

function TraceCard({ item }: { item: WorkItemDetail }) {
  const steps = item.current_plan?.steps ?? []
  const runId = item.current_plan?.agent_run_id
  return <section className="panel trace-card"><PanelTitle title="Agent Trace (Latest Run)" /><DetailRow label="Run ID" value={runId ? shortId(runId) : '-'} /><DetailRow label="Started" value={item.current_plan ? formatDate(item.current_plan.created_at) : '-'} /><DetailRow label="Steps" value={`${steps.length} steps`} /><DetailRow label="Status" value={item.current_plan ? (item.current_plan.requires_human ? 'Human action required' : 'Plan ready') : 'Not started'} /><div className="panel-actions"><button className="outline-button" disabled={!runId} onClick={() => runId && window.open(`/ui/agentops?run_id=${runId}`, '_blank')}><Link2 size={14} /> View Full Trace</button><button className="outline-button" onClick={() => window.open('/ui/agentops', '_blank')}><Boxes size={14} /> Open in AgentOps</button></div></section>
}

function CreateWorkItemModal({ documents, close, openItem }: { documents: DocumentSummary[]; close: () => void; openItem: (id: string) => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState('Review incoming invoice')
  const [type, setType] = useState('invoice_review')
  const [documentId, setDocumentId] = useState(documents[0]?.id ?? '')
  const [outcome, setOutcome] = useState('Validate the invoice and recommend the next safe action')
  const mutation = useMutation({
    mutationFn: () => api<{ work_item: WorkItemSummary }>('/backoffice/work-items', { method: 'POST', body: JSON.stringify({ title, work_type: type, linked_document_ids: documentId ? [documentId] : [], requested_outcome: outcome }) }),
    onSuccess: ({ work_item }) => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); close(); openItem(work_item.id) },
  })
  return <div className="modal-backdrop" role="presentation" onMouseDown={close}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="create-work-item-title" onMouseDown={(e) => e.stopPropagation()}><header><div><h2 id="create-work-item-title">New Document Task</h2><p>Create an accountable document operations task.</p></div><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={18} /></button></header><label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>Work type<select value={type} onChange={(e) => setType(e.target.value)}>{workTypes.map((value) => <option value={value} key={value}>{humanize(value)}</option>)}</select></label><label>Linked document<select value={documentId} onChange={(e) => setDocumentId(e.target.value)}><option value="">No linked document</option>{documents.map((doc) => <option value={doc.id} key={doc.id}>{doc.filename}</option>)}</select></label><label>Requested outcome<textarea value={outcome} onChange={(e) => setOutcome(e.target.value)} /></label>{mutation.error ? <p className="form-error">{(mutation.error as Error).message}</p> : null}<footer><button className="outline-button" onClick={close}>Cancel</button><button className="primary-button" disabled={mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <Loader2 className="spin" size={15} /> : <Plus size={15} />} Create Document Task</button></footer></section></div>
}

function EditWorkItemModal({ item, close }: { item: WorkItemDetail; close: () => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(item.title)
  const [priority, setPriority] = useState(item.priority)
  const [assignee, setAssignee] = useState(item.assignee === 'Unassigned' ? '' : item.assignee)
  const [outcome, setOutcome] = useState(item.requested_outcome)
  const [tags, setTags] = useState(item.tags.join(', '))
  const mutation = useMutation({
    mutationFn: () => api(`/backoffice/work-items/${item.id}`, { method: 'PATCH', body: JSON.stringify({ title, priority, assignee, requested_outcome: outcome, tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean) }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); queryClient.invalidateQueries({ queryKey: ['work-item', item.id] }); close() },
  })
  return <div className="modal-backdrop" role="presentation" onMouseDown={close}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="edit-work-item-title" onMouseDown={(event) => event.stopPropagation()}><header><div><h2 id="edit-work-item-title">Edit Document Task</h2><p>Update ownership and operational metadata.</p></div><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={18} /></button></header><label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Priority<select value={priority} onChange={(event) => setPriority(event.target.value)}>{['low','normal','high','urgent'].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Assignee<input value={assignee} placeholder="Reviewer name or team" onChange={(event) => setAssignee(event.target.value)} /></label><label>Requested outcome<textarea value={outcome} onChange={(event) => setOutcome(event.target.value)} /></label><label>Tags<input value={tags} placeholder="invoice, high-value, vendor" onChange={(event) => setTags(event.target.value)} /></label>{mutation.error ? <p className="form-error">{(mutation.error as Error).message}</p> : null}<footer><button className="outline-button" onClick={close}>Cancel</button><button className="primary-button" disabled={!title.trim() || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <Loader2 className="spin" size={15} /> : <Check size={15} />} Save Changes</button></footer></section></div>
}

function SectionPage({
  page,
  workspace,
  loadingWorkspace,
  openItem,
}: {
  page: PageId
  workspace?: Workspace
  loadingWorkspace: boolean
  openItem: (id: string) => void
}) {
  const needsDetails = ['drafts', 'approvals', 'policies', 'guardrails', 'evaluation'].includes(page)
  const details = useQuery({
    queryKey: ['work-item-aggregate', workspace?.work_items.map((item) => item.id).join(',')],
    queryFn: () => Promise.all((workspace?.work_items ?? []).map((item) => api<{ work_item: WorkItemDetail }>(`/backoffice/work-items/${item.id}`).then((data) => data.work_item))),
    enabled: needsDetails && Boolean(workspace),
  })
  const runs = useQuery({
    queryKey: ['agentops-runs'],
    queryFn: () => api<{ runs: AgentRun[] }>('/agentops/runs?limit=50'),
    enabled: ['runs', 'reliability', 'evaluation'].includes(page),
  })
  const reliability = useQuery({
    queryKey: ['agentops-summary'],
    queryFn: () => api<{ summary: ReliabilitySummary }>('/agentops/summary?limit=100'),
    enabled: page === 'reliability',
  })
  const agentScenarios = useQuery({
    queryKey: ['agent-scenarios'],
    queryFn: () => api<ScenarioDataset>('/agentops/scenarios'),
    enabled: ['evaluation', 'datasets'].includes(page),
  })
  const backofficeScenarios = useQuery({
    queryKey: ['backoffice-scenarios'],
    queryFn: () => api<ScenarioDataset>('/agentops/backoffice/scenarios'),
    enabled: ['evaluation', 'datasets'].includes(page),
  })
  const evaluations = useQuery({
    queryKey: ['scenario-evaluations'],
    queryFn: () => api<{ evaluations: ScenarioEvaluation[] }>('/agentops/evaluations?limit=100'),
    enabled: page === 'evaluation',
  })
  const regression = useQuery({
    queryKey: ['agentops-regression'],
    queryFn: () => api<{ regression: Regression }>('/agentops/regression', { method: 'POST', body: JSON.stringify({ previous_limit: 20, current_limit: 20 }) }),
    enabled: page === 'reliability',
  })
  const promptVersions = useQuery({
    queryKey: ['agentops-prompt-versions'],
    queryFn: () => api<{ prompt_versions: PromptVersionMetric[] }>('/agentops/prompt-versions?limit=100'),
    enabled: page === 'reliability',
  })
  const operations = useQuery({
    queryKey: ['operations-jobs'],
    queryFn: () => api<OperationsJobs>('/operations/jobs'),
    enabled: page === 'operations',
  })

  const content = () => {
    if (loadingWorkspace || (needsDetails && details.isLoading)) return <LoadingState />
    if (details.error || runs.error || reliability.error || agentScenarios.error || backofficeScenarios.error || evaluations.error || regression.error || promptVersions.error || operations.error) {
      const error = details.error ?? runs.error ?? reliability.error ?? agentScenarios.error ?? backofficeScenarios.error ?? evaluations.error ?? regression.error ?? promptVersions.error ?? operations.error
      return <ErrorState message={(error as Error).message} retry={() => { details.refetch(); runs.refetch(); reliability.refetch(); agentScenarios.refetch(); backofficeScenarios.refetch(); evaluations.refetch(); regression.refetch(); promptVersions.refetch(); operations.refetch() }} />
    }
    if (page === 'runs') return <RunsPage runs={runs.data?.runs ?? []} />
    if (page === 'drafts') return <DraftsPage items={details.data ?? []} openItem={openItem} />
    if (page === 'approvals') return <ApprovalsPage items={details.data ?? []} openItem={openItem} />
    if (page === 'operations') return <OperationalControlsPage data={operations.data} />
    if (page === 'policies') return <PoliciesPage items={details.data ?? []} />
    if (page === 'guardrails') return <GuardrailsPage items={details.data ?? []} />
    if (page === 'integrations') return <IntegrationsPage workspace={workspace} />
    if (page === 'settings') return <SettingsPage workspace={workspace} />
    if (page === 'reliability') return <ReliabilityPage summary={reliability.data?.summary} runs={runs.data?.runs ?? []} regression={regression.data?.regression} promptVersions={promptVersions.data?.prompt_versions ?? []} />
    if (page === 'evaluation') return <EvaluationPage agent={agentScenarios.data} backoffice={backofficeScenarios.data} runs={runs.data?.runs ?? []} items={details.data ?? []} evaluations={evaluations.data?.evaluations ?? []} />
    return <DatasetsPage agent={agentScenarios.data} backoffice={backofficeScenarios.data} />
  }

  return (
    <main className="section-page">
      <SectionHeading page={page} />
      {content()}
    </main>
  )
}

function SectionHeading({ page }: { page: PageId }) {
  const copy: Record<PageId, string> = {
    runs: 'Inspect the stored technical trace behind each AI-assisted work decision.',
    drafts: 'Review AI-generated accounting notes, messages, and export previews.',
    approvals: 'Resolve the human decisions blocking controlled execution.',
    operations: 'Inspect worker failures, controlled retries, and authorized audit evidence.',
    policies: 'See the backend rules that decide whether a document action is allowed.',
    guardrails: 'Monitor the safety boundaries enforced across document work.',
    integrations: 'Manage the systems this document workflow can read from or write to.',
    settings: 'Configure this local workspace and its operator access.',
    reliability: 'Inspect local quality, safety, escalation, and failure evidence.',
    evaluation: 'Run deterministic reliability checks against stored traces and plans.',
    datasets: 'Inspect the versioned test scenarios behind reliability results.',
  }
  return <section className="section-heading"><div><span className="section-eyebrow">{pageGroup(page)}</span><h2>{pageTitle(page)}</h2><p>{copy[page]}</p></div><button className="outline-button" onClick={() => queryClient.invalidateQueries()}><RefreshCw size={15} /> Refresh data</button></section>
}

function RunsPage({ runs }: { runs: AgentRun[] }) {
  const [selected, setSelected] = useState<string | null>(runs[0]?.id ?? null)
  const current = runs.find((run) => run.id === selected) ?? runs[0]
  return <div className="split-page"><section className="data-panel"><DataPanelHeader icon={<Activity size={17} />} title="Recent Runs" count={runs.length} /><div className="run-list">{runs.map((run) => <button className={current?.id === run.id ? 'active' : ''} key={run.id} onClick={() => setSelected(run.id)}><span className={`run-dot ${run.evaluation.successful_completion ? 'success' : 'warning'}`} /><div><strong>{humanize(run.intent)}</strong><p>{run.request}</p><small>{formatDate(run.created_at)} · {run.prompt_version}</small></div><Status value={run.evaluation.successful_completion ? 'resolved' : run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></button>)}</div>{runs.length === 0 ? <EmptyState title="No agent runs" body="Use the copilot or evaluation workflow to create trace data." /> : null}</section><section className="data-panel run-detail"><DataPanelHeader icon={<Workflow size={17} />} title="Run Trace" />{current ? <><div className="run-hero"><span className="work-icon purple"><BotIcon /></span><div><span>Run {shortId(current.id)}</span><h3>{humanize(current.intent)}</h3><p>{current.evaluation.decision_reason}</p></div></div><div className="stats-grid compact"><Stat label="Confidence" value={`${Math.round(current.evaluation.confidence_score * 100)}%`} /><Stat label="Tool calls" value={current.evaluation.tool_call_count} /><Stat label="Cost" value={currency(current.evaluation.estimated_cost_usd)} /><Stat label="Blocked" value={current.evaluation.blocked_action_count} /></div><div className="trace-comparison"><TraceValue label="Expected tool" value={current.evaluation.expected_tool ?? 'Not scored'} /><ChevronRight size={16} /><TraceValue label="Selected tool" value={current.evaluation.selected_tool ?? 'No tool'} /></div>{current.evaluation.failure_type ? <div className="notice danger"><AlertTriangle size={16} /><div><strong>{humanize(current.evaluation.failure_type)}</strong><p>This run was classified by the AgentOps failure taxonomy.</p></div></div> : <div className="notice success"><CheckCircle2 size={16} /><div><strong>Trace passed reliability checks</strong><p>No failure type was recorded for this run.</p></div></div>}</> : <EmptyState title="Select a run" body="Run detail and evaluation evidence will appear here." />}</section></div>
}

function DraftsPage({ items, openItem }: { items: WorkItemDetail[]; openItem: (id: string) => void }) {
  const drafts = items.flatMap((item) => item.drafts.map((draft) => ({ draft, item })))
  return <section className="data-panel"><DataPanelHeader icon={<FileClock size={17} />} title="Draft Library" count={drafts.length} /><div className="artifact-grid">{drafts.map(({ draft, item }) => <article className="artifact-card" key={draft.id}><header><span className="work-icon purple"><FileText size={16} /></span><div><TypeBadge value={item.work_type} /><h3>{humanize(draft.draft_type)}</h3></div><Status value={draft.status} /></header><pre>{draft.preview_content}</pre><footer><span>{formatDate(draft.created_at)}</span><button className="outline-button" onClick={() => openItem(item.id)}>Open work item <ChevronRight size={14} /></button></footer></article>)}</div>{drafts.length === 0 ? <EmptyState title="No drafts available" body="Generate a plan containing a draft action." /> : null}</section>
}

function ApprovalsPage({ items, openItem }: { items: WorkItemDetail[]; openItem: (id: string) => void }) {
  const approvals = items.flatMap((item) => item.approvals.map((approval) => ({ approval, item })))
  const pending = approvals.filter(({ approval }) => approval.status === 'pending').length
  const highRisk = approvals.filter(({ item }) => ['high', 'urgent'].includes(item.priority)).length
  return <><div className="approval-summary"><Stat label="Pending decisions" value={pending} icon={<FileClock size={18} />} /><Stat label="High-risk gates" value={highRisk} icon={<ShieldCheck size={18} />} /><Stat label="Decisions recorded" value={approvals.length - pending} icon={<ClipboardCheck size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<ClipboardCheck size={17} />} title="Human Approval Inbox" count={approvals.length} /><div className="approval-table enhanced">{approvals.map(({ approval, item }) => { const signals = exceptionSignals(item); const step = item.current_plan?.steps.find((candidate) => candidate.id === approval.action_step_id); return <article key={approval.id}><span className={`approval-icon ${approval.status}`}><ClipboardCheck size={17} /></span><div><h3>{item.title}</h3><p>{businessId(item)} · {signals[0]?.label ?? 'Policy approval gate'}</p><div className="exception-chip-row">{signals.slice(0, 2).map((signal) => <span className={`exception-chip exception-${signal.tone}`} key={signal.label}>{signal.label}</span>)}</div></div><div className="approval-proposal"><small>Proposed action</small><strong>{humanize(step?.action_type ?? 'Awaiting plan')}</strong></div><Priority value={step?.risk_level ?? item.priority} /><Status value={approval.status} /><span>{formatDate(approval.created_at)}</span><button className="outline-button" onClick={() => openItem(item.id)}>Review decision <ChevronRight size={14} /></button></article> })}</div>{approvals.length === 0 ? <EmptyState title="Approval inbox is clear" body="New human gates will appear here when a plan requests confirmation." /> : null}</section></>
}

function OperationalControlsPage({ data }: { data?: OperationsJobs }) {
  const queryClient = useQueryClient()
  const [toast, setToast] = useState<{ kind: 'success' | 'danger'; message: string } | null>(null)
  const retry = useMutation({
    mutationFn: (jobId: string) => api(`/operations/jobs/${jobId}/retry`, { method: 'POST' }),
    onSuccess: () => {
      setToast({ kind: 'success', message: 'Job was queued for a controlled retry.' })
      queryClient.invalidateQueries({ queryKey: ['operations-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
    },
    onError: (error: Error) => setToast({ kind: 'danger', message: error.message }),
  })
  const downloadAudit = async () => {
    try {
      const response = await fetch('/operations/audit.csv', { credentials: 'same-origin' })
      if (!response.ok) throw new Error('Audit export failed.')
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'audit-log.csv'
      anchor.click()
      URL.revokeObjectURL(url)
      setToast({ kind: 'success', message: 'Authorized audit log exported.' })
    } catch (error) {
      setToast({ kind: 'danger', message: (error as Error).message })
    }
  }
  return <><div className="stats-grid"><Stat label="Worker status" value={humanize(data?.worker.status ?? 'checking')} icon={<CircleGauge size={18} />} /><Stat label="Queued jobs" value={data?.worker.queued_jobs ?? 0} icon={<FileClock size={18} />} /><Stat label="Failed jobs" value={data?.worker.failed_jobs ?? 0} icon={<AlertTriangle size={18} />} /><Stat label="Stalled jobs" value={data?.worker.stalled_jobs ?? 0} icon={<Activity size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Worker Health" /><div className={`notice ${data?.worker.status === 'degraded' ? 'danger' : 'success'}`}><ShieldCheck size={16} /><div><strong>{humanize(data?.worker.status ?? 'checking')}</strong><p>{data?.worker.evidence}</p></div></div><div className="panel-actions"><button className="outline-button" onClick={downloadAudit}><FileText size={14} /> Export audit CSV</button></div></section><section className="data-panel"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Failed And Dead-Letter Jobs" count={data?.failed_jobs.length ?? 0} /><div className="approval-table">{data?.failed_jobs.map((job) => <article key={job.id}><span className="approval-icon rejected"><AlertTriangle size={17} /></span><div><h3>Document {shortId(job.document_id)}</h3><p>{job.error_message || 'Persistent processing failure.'}</p></div><Status value={job.status} /><span>{job.provider_name ?? 'unknown provider'} · {job.attempt_count} attempts</span><button className="outline-button" disabled={retry.isPending} onClick={() => retry.mutate(job.id)}><RefreshCw size={14} /> Retry</button></article>)}</div>{!data?.failed_jobs.length ? <EmptyState title="No failed jobs" body="Worker failures and dead-letter jobs will remain visible here until resolved." /> : null}</section>{toast ? <div className={`app-toast ${toast.kind}`} role="status"><span>{toast.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}</span><p>{toast.message}</p><button onClick={() => setToast(null)}><X size={14} /></button></div> : null}</>
}

function PoliciesPage({ items }: { items: WorkItemDetail[] }) {
  const decisions = items.flatMap((item) => item.policy_decisions.map((decision) => ({ decision, item })))
  const allowed = decisions.filter(({ decision }) => decision.allowed).length
  return <><div className="stats-grid"><Stat label="Policy decisions" value={decisions.length} icon={<FileCheck2 size={18} />} /><Stat label="Allowed actions" value={allowed} icon={<CheckCircle2 size={18} />} /><Stat label="Confirmation gates" value={decisions.filter(({ decision }) => decision.requires_confirmation).length} icon={<UserRound size={18} />} /><Stat label="Blocked actions" value={decisions.length - allowed} icon={<ShieldCheck size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<FileCheck2 size={17} />} title="Policy Decision Log" count={decisions.length} /><div className="policy-list">{decisions.map(({ decision, item }) => <article key={decision.id}><div className="policy-main"><span className={`policy-result ${decision.allowed ? 'allowed' : 'blocked'}`}>{decision.allowed ? <Check size={15} /> : <X size={15} />}</span><div><h3>{humanize(decision.action_type)}</h3><p>{decision.reason}</p><small>{item.title} · {formatDate(item.updated_at)}</small></div></div><div className="policy-tags"><Priority value={decision.risk_level} /><span className="type-badge">{humanize(decision.autonomy_level)}</span>{decision.requires_confirmation ? <Status value="awaiting_human" /> : <Status value="approved" />}</div></article>)}</div></section></>
}

function GuardrailsPage({ items }: { items: WorkItemDetail[] }) {
  const decisions = items.flatMap((item) => item.policy_decisions)
  const guardrails = [
    ['Human approval for risky actions', 'Requires explicit operator confirmation before medium or high-risk execution.', decisions.filter((d) => d.requires_confirmation).length, UserRound],
    ['Workspace isolation', 'Every document, work item, run, and approval remains scoped to its workspace.', items.length, ShieldCheck],
    ['Unsafe action prevention', 'Policy decisions can block tools that exceed the configured autonomy boundary.', decisions.filter((d) => !d.allowed).length, AlertTriangle],
    ['Evidence before execution', 'Document-dependent actions require linked and processed source evidence.', items.filter((i) => i.linked_document_ids.length > 0).length, FileCheck2],
    ['Auditable execution', 'Plans, drafts, approvals, policy decisions, and tool results remain traceable.', decisions.length, Activity],
  ] as const
  return <><section className="guardrail-hero"><div><span><ShieldCheck size={21} /></span><div><p>ACTIVE GOVERNANCE</p><h2>Bounded autonomy, enforced by design</h2><small>These controls are application boundaries, not prompt-only instructions.</small></div></div><Status value="approved" /></section><div className="guardrail-grid">{guardrails.map(([title, body, events, Icon]) => <article key={title}><header><span><Icon size={18} /></span><Status value="approved" /></header><h3>{title}</h3><p>{body}</p><footer><strong>{events}</strong><span>observed records</span></footer></article>)}</div></>
}

function IntegrationsPage({ workspace }: { workspace?: Workspace }) {
  const queryClient = useQueryClient()
  const statuses = useQuery({ queryKey: ['integration-status'], queryFn: () => api<IntegrationStatus>('/integrations/status') })
  const test = useMutation({
    mutationFn: (name: string) => api(`/integrations/${name}/test`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['integration-status'] }),
  })
  const icons: Record<string, typeof Database> = { email: FileClock, accounting: Link2, document_storage: Boxes, database: Database }
  if (statuses.isLoading) return <LoadingState />
  if (statuses.error) return <ErrorState message={statuses.error.message} retry={() => statuses.refetch()} />
  return <section className="integration-grid">{statuses.data?.integrations.map((integration) => { const Icon = icons[integration.name] ?? Network; return <article key={integration.name}><header><span className="integration-icon"><Icon size={20} /></span><Status value={integration.status} /></header><h3>{humanize(integration.name)}</h3><p>{integration.evidence}</p><DetailRow label="Provider" value={integration.provider} /><DetailRow label="Mode" value={integration.sandbox_mode ? 'Sandbox / local' : 'Live'} /><footer><span>{integration.configuration_ready ? 'Configuration ready' : 'Credentials required'}</span><button className="outline-button" disabled={test.isPending} onClick={() => test.mutate(integration.name)}><RefreshCw size={14} /> Test connection</button></footer></article> })}<article><header><span className="integration-icon"><Activity size={20} /></span><Status value="healthy" /></header><h3>AgentOps telemetry</h3><p>Automatic local trace and evaluation persistence.</p><footer><span>{workspace?.work_items.length ?? 0} work items observed</span></footer></article></section>
}

function SettingsPage({ workspace }: { workspace?: Workspace }) {
  const [saved, setSaved] = useState(false)
  const providers = useQuery({ queryKey: ['provider-health'], queryFn: () => api<ProviderHealth>('/providers/health') })
  const integrations = useQuery({ queryKey: ['integration-status'], queryFn: () => api<IntegrationStatus>('/integrations/status') })
  const refresh = () => { setSaved(true); queryClient.invalidateQueries() }
  return <div className="settings-layout"><section className="data-panel settings-panel"><DataPanelHeader icon={<Settings size={17} />} title="Workspace Configuration" /><label><span>Workspace</span><input value={workspace?.workspace_id ?? 'default'} disabled /></label><DetailRow label="Authentication" value="Opaque HttpOnly server session" /><DetailRow label="Credential storage" value="Server-side only; no browser token" /><label><span>Backend endpoint</span><input value="Same origin" disabled /></label><label><span>Frontend endpoint</span><input value={window.location.origin} disabled /></label><div className="settings-actions"><button className="primary-button" onClick={refresh}><RefreshCw size={15} /> Refresh configuration</button>{saved ? <span><CheckCircle2 size={14} /> Refreshed</span> : null}</div></section><section className="data-panel settings-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Runtime And Providers" /><div className="mode-banner"><strong>Production-shaped runtime</strong><p>Secrets stay in the server-side .env file and are never returned to this browser.</p></div>{providers.data?.providers.map((provider) => <DetailRow key={provider.role} label={`${humanize(provider.role)} provider`} value={`${provider.provider_name} · ${humanize(provider.status)}`} />)}{integrations.data?.integrations.map((integration) => <DetailRow key={integration.name} label={humanize(integration.name)} value={`${integration.provider} · ${humanize(integration.status)}`} />)}<DetailRow label="Fallback state" value={providers.data?.overall_status === 'healthy' ? 'Local deterministic providers active' : 'Real provider configured; mock remains available via .env'} /><DetailRow label="Telemetry" value="Durable local AgentOps" /></section></div>
}

function ReliabilityPage({ summary, runs, regression, promptVersions }: { summary?: ReliabilitySummary; runs: AgentRun[]; regression?: Regression; promptVersions: PromptVersionMetric[] }) {
  const metrics = [
    ['Tool Selection Accuracy', percent(summary?.tool_selection_accuracy), 'Expected vs selected tools'],
    ['Unsafe Action Prevention', percent(summary?.unsafe_action_prevention_rate), 'Blocked unsafe attempts'],
    ['Successful Completion', percent(summary?.successful_completion_rate), 'Runs completing safely'],
    ['Escalation Rate', percent(summary?.escalation_rate), 'Runs sent to a human'],
  ]
  const enoughObservations = (summary?.total_runs ?? 0) >= 5
  const failedRuns = runs.filter((run) => run.evaluation.failure_type || !run.evaluation.successful_completion)
  return <>
    <EvidenceScope title="Local evaluation evidence" detail={`Metrics below are calculated from ${summary?.total_runs ?? 0} stored local run${(summary?.total_runs ?? 0) === 1 ? '' : 's'}. They are not production telemetry or a general model-quality claim.`} />
    <div className="reliability-metrics">{metrics.map(([label, value, note]) => <article key={label}><div className="ring"><span>{value}</span></div><div><h3>{label}</h3><p>{note}</p></div></article>)}</div>
    <div className="analytics-grid">
      <section className="data-panel"><DataPanelHeader icon={<Activity size={17} />} title="Recent Document Operation Runs" /><div className="signal-list">{runs.slice(0, 8).map((run) => <div key={run.id}><span className={`run-dot ${run.evaluation.successful_completion ? 'success' : 'warning'}`} /><strong>{humanize(run.intent)}</strong><span>{Math.round(run.evaluation.confidence_score * 100)}% confidence</span><Status value={run.evaluation.successful_completion ? 'resolved' : run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></div>)}</div>{runs.length === 0 ? <EmptyState title="No reliability signals yet" body="Create application runs to populate this dashboard." /> : null}</section>
      <section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Operational Efficiency" /><div className="large-stat"><span>Average confidence</span><strong>{percent(summary?.average_confidence)}</strong></div><DetailRow label="Evaluated runs" value={summary?.evaluated_runs ?? 0} /><DetailRow label="Average tool calls" value={decimal(summary?.average_tool_calls_per_task)} /><DetailRow label="Average latency" value={`${decimal(summary?.average_latency_ms)} ms`} /><DetailRow label="Estimated cost / run" value={currency(summary?.estimated_cost_per_run)} /></section>
      <section className="data-panel"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Error Trend" />{enoughObservations ? <div className="failure-bars">{(summary?.failure_trend ?? []).map(({ failure_type, count }) => <div key={failure_type}><span>{humanize(failure_type)}</span><i><b style={{ width: `${Math.min(100, count * 20)}%` }} /></i><strong>{count}</strong></div>)}</div> : <EmptyState title="Not enough observations" body="At least five runs are required before showing an error trend." />}</section>
      <section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Confidence Calibration" />{enoughObservations ? <div className="failure-bars">{Object.entries(summary?.confidence_distribution ?? {}).map(([name, count]) => <div key={name}><span>{humanize(name)}</span><i><b style={{ width: `${Math.min(100, count / Math.max(summary?.total_runs ?? 1, 1) * 100)}%` }} /></i><strong>{count}</strong></div>)}</div> : <EmptyState title="Calibration pending" body="Confidence distribution appears after five observed runs." />}</section>
      <section className="data-panel"><DataPanelHeader icon={<Workflow size={17} />} title="Prompt / Planner Versions" />{promptVersions.map((version) => <div className="trace-comparison" key={version.prompt_version}><TraceValue label="Version" value={version.prompt_version} /><TraceValue label="Runs" value={String(version.total_runs)} /><TraceValue label="Accuracy" value={percent(version.tool_selection_accuracy)} /></div>)}</section>
      <section className="data-panel"><DataPanelHeader icon={<Columns3 size={17} />} title="Regression Comparison" />{regression?.deltas.map((delta) => <div className="trace-comparison" key={delta.metric}><TraceValue label="Metric" value={delta.metric} /><TraceValue label="Previous" value={percent(delta.previous)} /><TraceValue label="Current" value={percent(delta.current)} /><Status value={delta.regressed ? 'failed' : 'approved'} /></div>)}{!regression?.deltas.length ? <EmptyState title="No comparison window" body="More runs are needed to compare current and previous windows." /> : null}</section>
      <section className="data-panel known-failures"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Known Failures" count={failedRuns.length} />{failedRuns.slice(0, 6).map((run) => <article key={run.id}><span className="approval-icon rejected"><AlertTriangle size={15} /></span><div><strong>{humanize(run.evaluation.failure_type ?? 'Incomplete run')}</strong><p>{run.evaluation.decision_reason}</p><small>{humanize(run.intent)} · Run {shortId(run.id)} · {formatDate(run.created_at)}</small></div><Status value={run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></article>)}{!failedRuns.length ? <EmptyState title="No known failures in this sample" body="This only describes the stored local observation set." /> : null}</section>
      <section className="data-panel evidence-limitations"><DataPanelHeader icon={<ShieldCheck size={17} />} title="Known Limitations" /><p><Check size={14} /> Invoice is the only complete document schema in the current workflow.</p><p><Check size={14} /> Metrics depend on stored local runs and may have a small sample size.</p><p><Check size={14} /> Confidence distribution is descriptive, not calibrated against production outcomes.</p><p><Check size={14} /> Provider and external integration quality are evaluated separately.</p></section>
    </div>
  </>
}

function EvaluationPage({ agent, backoffice, runs, items, evaluations }: { agent?: ScenarioDataset; backoffice?: ScenarioDataset; runs: AgentRun[]; items: WorkItemDetail[]; evaluations: ScenarioEvaluation[] }) {
  const [tab, setTab] = useState<'agent' | 'backoffice'>('backoffice')
  const [targetId, setTargetId] = useState('')
  const [results, setResults] = useState<Record<string, ScenarioResult>>({})
  useEffect(() => {
    setResults(Object.fromEntries(evaluations.map((record) => [
      record.scenario_id,
      { passed: record.passed, checks: record.evidence.checks ?? {}, ...record.evidence },
    ])))
  }, [evaluations])
  const dataset = tab === 'agent' ? agent : backoffice
  const targets = tab === 'agent'
    ? runs.map((run) => ({ id: run.id, label: `${humanize(run.intent)} · ${shortId(run.id)}` }))
    : items.filter((item) => item.current_plan).map((item) => ({ id: item.id, label: `${item.title} · ${shortId(item.current_plan!.id)}` }))
  const selectedTarget = targets.some((target) => target.id === targetId) ? targetId : targets[0]?.id ?? ''
  const evaluation = useMutation({
    mutationFn: ({ scenarioId }: { scenarioId: string }) => api<{ result: ScenarioResult }>(
      tab === 'agent' ? '/agentops/scenarios/evaluate' : '/agentops/backoffice/scenarios/evaluate',
      { method: 'POST', body: JSON.stringify({ scenario_id: scenarioId, [tab === 'agent' ? 'run_id' : 'work_item_id']: selectedTarget }) },
    ),
    onSuccess: ({ result }, { scenarioId }) => {
      setResults((current) => ({ ...current, [scenarioId]: result }))
      queryClient.invalidateQueries({ queryKey: ['scenario-evaluations'] })
    },
  })
  const completedResults = Object.values(results)
  const passedResults = completedResults.filter((result) => result.passed).length
  return <>
    <EvidenceScope title="Deterministic case evaluation" detail="Each result compares one stored plan or run with a versioned expected contract. Passing a case does not imply broad document or production coverage." />
    <div className="stats-grid"><Stat label="Agent scenarios" value={agent?.scenario_count ?? 0} icon={<BotIcon />} /><Stat label="Backoffice scenarios" value={backoffice?.scenario_count ?? 0} icon={<Workflow size={18} />} /><Stat label="Observed runs" value={runs.length} icon={<Activity size={18} />} /><Stat label="Evaluation mode" value="Deterministic" icon={<CheckCircle2 size={18} />} /></div>
    <div className="evaluation-result-strip"><strong>{completedResults.length ? `${passedResults} of ${completedResults.length} evaluated cases passed` : 'No cases evaluated yet'}</strong><span>Results are persisted against scenario IDs and versioned datasets.</span>{completedResults.some((result) => result.actual_document_type || result.actual_operation_type) ? <div className="scenario-tags">{completedResults.map((result, index) => <span key={index}>{[result.actual_document_type && `Actual document: ${humanize(result.actual_document_type)}`, result.actual_operation_type && `Actual operation: ${humanize(result.actual_operation_type)}`].filter(Boolean).join(' · ')}</span>)}</div> : null}</div>
    <section className="data-panel">
      <div className="evaluation-toolbar">
        <div className="segment-control"><button className={tab === 'backoffice' ? 'active' : ''} onClick={() => setTab('backoffice')}>Backoffice plans</button><button className={tab === 'agent' ? 'active' : ''} onClick={() => setTab('agent')}>Agent tools</button></div>
        <select value={selectedTarget} onChange={(event) => setTargetId(event.target.value)} aria-label="Evaluation target">{targets.length ? targets.map((target) => <option value={target.id} key={target.id}>{target.label}</option>) : <option value="">No compatible observations</option>}</select>
        <span>{dataset?.dataset_id} · {dataset?.dataset_version}</span>
      </div>
      <div className="scenario-list">{dataset?.scenarios.map((scenario, index) => {
        const result = results[scenario.id]
        return <article key={scenario.id}><span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><div><h3>{scenario.title ?? humanize(scenario.id)}</h3><p>{scenario.message ?? `${humanize(scenario.work_type ?? 'backoffice')} scenario with deterministic plan expectations.`}</p><div className="scenario-tags">{scenario.document_type ? <span>Document: {humanize(scenario.document_type)}</span> : null}{scenario.operation_type ? <span>Operation: {humanize(scenario.operation_type)}</span> : null}{scenario.expected_tool ? <span>Tool: {humanize(scenario.expected_tool)}</span> : null}{scenario.expected_risk ? <span>Risk: {humanize(scenario.expected_risk)}</span> : null}{scenario.expected_confidence ? <span>Confidence: {scenario.expected_confidence}</span> : null}{result ? <Status value={result.passed ? 'approved' : 'failed'} /> : null}</div>{result ? <small>{Object.entries(result.checks).map(([name, passed]) => `${humanize(name)}: ${passed ? 'pass' : 'fail'}`).join(' · ')}</small> : null}<ScenarioResultEvidence scenario={scenario} result={result} /></div><button className="outline-button" disabled={!selectedTarget || evaluation.isPending} onClick={() => evaluation.mutate({ scenarioId: scenario.id })}>{evaluation.isPending ? <Loader2 size={14} /> : <Play size={14} />} Evaluate</button></article>
      })}</div>
      {evaluation.error ? <div className="notice danger"><AlertTriangle size={16} /><p>{evaluation.error.message}</p></div> : null}
    </section>
  </>
}

function DatasetsPage({ agent, backoffice }: { agent?: ScenarioDataset; backoffice?: ScenarioDataset }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  return <><EvidenceScope title="Versioned local test contracts" detail="These datasets define reproducible expectations for the implemented invoice workflow and agent tools. They are test fixtures, not customer documents." /><div className="dataset-grid">{[agent, backoffice].filter(Boolean).map((dataset) => {
    const selected = dataset!.scenarios.find((scenario) => scenario.id === scenarioId)
    return <section className="dataset-card" key={dataset!.dataset_id}><header><span className="dataset-icon"><Database size={22} /></span><div><span>VERSIONED DATASET</span><h3>{humanize(dataset!.dataset_id)}</h3></div><Status value="approved" /></header><p>{dataset!.description}</p><div className="dataset-meta"><div><span>Current version</span><strong>{dataset!.dataset_version}</strong></div><div><span>Version history</span><strong>{dataset!.dataset_version} (current)</strong></div><div><span>Scenarios</span><strong>{dataset!.scenario_count}</strong></div></div><div className="dataset-preview">{dataset!.scenarios.map((scenario) => <button key={scenario.id} onClick={() => setScenarioId(scenario.id)}><FileText size={14} /><span>{scenario.title ?? scenario.message ?? humanize(scenario.id)}</span><ChevronRight size={14} /></button>)}</div>{selected ? <div className="notice"><FileText size={16} /><div><strong>{selected.title ?? humanize(selected.id)}</strong><p>{selected.message ?? `Expected workflow: ${selected.expected_plan_steps?.map(humanize).join(' → ') ?? humanize(selected.work_type ?? 'agent scenario')}`}</p><ScenarioMetaTags scenario={selected} /><small>Scenario ID: {selected.id}</small></div></div> : null}{expanded === dataset!.dataset_id ? <div className="dataset-preview"><strong>Required schema fields</strong>{(dataset!.required_fields ?? Object.keys(dataset!.scenarios[0] ?? {})).map((field) => <div key={field}><Check size={14} /><span>{field}</span></div>)}</div> : null}<footer><button className="outline-button" onClick={() => setExpanded(expanded === dataset!.dataset_id ? null : dataset!.dataset_id)}><FileText size={14} /> {expanded === dataset!.dataset_id ? 'Hide schema' : 'Inspect schema'}</button><span>Reproducible evaluation contract</span></footer></section>
  })}</div></>
}

function ScenarioMetaTags({ scenario }: { scenario: Scenario }) {
  if (!scenario.document_type && !scenario.operation_type) return null
  return <div className="scenario-tags">{scenario.document_type ? <span>Document: {humanize(scenario.document_type)}</span> : null}{scenario.operation_type ? <span>Operation: {humanize(scenario.operation_type)}</span> : null}</div>
}

function ScenarioResultEvidence({ scenario, result }: { scenario: Scenario; result?: ScenarioResult }) {
  if (!result || !(scenario.document_type || scenario.operation_type || result.actual_document_type || result.actual_operation_type)) return null
  return <div className="scenario-evidence"><div><span>Expected document</span><strong>{humanize(result.expected_document_type ?? scenario.document_type ?? 'not scored')}</strong></div><div><span>Actual document</span><strong>{humanize(result.actual_document_type ?? 'not scored')}</strong></div><div><span>Expected operation</span><strong>{humanize(result.expected_operation_type ?? scenario.operation_type ?? 'not scored')}</strong></div><div><span>Actual operation</span><strong>{humanize(result.actual_operation_type ?? 'not scored')}</strong></div></div>
}

function EvidenceScope({ title, detail }: { title: string; detail: string }) {
  return <section className="evidence-scope"><ShieldCheck size={18} /><div><strong>{title}</strong><p>{detail}</p></div><span>Scope disclosed</span></section>
}

function DataPanelHeader({ icon, title, count }: { icon: React.ReactNode; title: string; count?: number }) {
  return <header className="data-panel-header"><span>{icon}</span><h2>{title}</h2>{count !== undefined ? <b>{count}</b> : null}</header>
}
function Stat({ label, value, icon }: { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
  return <article className="stat-card">{icon ? <span>{icon}</span> : null}<div><p>{label}</p><strong>{value}</strong></div></article>
}
function TraceValue({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{humanize(value)}</strong></div>
}
function BotIcon() {
  return <Sparkles size={18} />
}

function DocumentsPage({ workspace, loading }: { workspace?: Workspace; loading: boolean }) {
  return <main className="queue-page"><section className="page-heading"><div><h2>Document Library</h2><p>Source records available to document operations workflows.</p></div></section><section className="queue-surface document-list">{loading ? <LoadingState /> : workspace?.documents.map((doc) => <article key={doc.id}><WorkIcon type="invoice_review" /><div><strong>{doc.filename}</strong><span>{shortId(doc.id)} · {formatDate(doc.created_at)}</span><SchemaMeta document={doc} extraction={null} compact /></div><Status value={doc.status} /></article>)}</section></main>
}

function DocumentTab({ document, documentDetail, extraction, loading }: { document?: DocumentSummary; documentDetail?: ApiDocument; extraction: Extraction | null; loading: boolean }) {
  if (loading) return <LoadingState />
  if (!document) return <EmptyState title="No linked document" body="Link a document to inspect extraction and validation evidence." />
  return <div className="document-review-layout"><AuthenticatedPdfPreview document={document} /><section className="panel document-evidence"><PanelTitle title="Extraction Evidence" action={<Status value={document.status} />} /><SchemaMeta document={documentDetail} extraction={extraction} /><div className="invoice-fields">{invoiceFields(extraction).map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong><small><i /> Stored extraction</small></div>)}</div>{extraction?.confidence?.length ? <div className="evidence-list">{extraction.confidence.map((evidence) => <article key={evidence.field_name}><strong>{humanize(evidence.field_name)}</strong><span>{evidence.score == null ? 'Not scored' : `${Math.round(evidence.score * 100)}%`}</span><p>{evidence.source_text || 'No source excerpt stored.'}</p></article>)}</div> : null}{extraction?.validation?.length ? <div className="validation-list">{extraction.validation.map((issue, index) => <p key={index}><AlertTriangle size={14} /><span>{issue.message}</span></p>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No validation blockers.</div>}</section></div>
}

function SchemaMeta({ document, extraction, compact = false }: { document?: ApiDocument | DocumentSummary; extraction: Extraction | null; compact?: boolean }) {
  const documentType = extraction?.document_type ?? document?.document_type ?? 'invoice'
  const schema = extraction?.schema_version ?? document?.supported_extraction_schema ?? 'invoice_v1'
  return <div className={`schema-meta ${compact ? 'compact' : ''}`}><span><FileText size={12} /> {humanize(documentType)}</span><span><Database size={12} /> {schema}</span></div>
}

function AuthenticatedPdfPreview({ document }: { document: DocumentSummary }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    let objectUrl = ''
    fetch(`/documents/${document.id}/content`, { credentials: 'same-origin' }).then((response) => response.blob()).then((blob) => { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }).catch(() => setUrl(''))
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [document.id])
  return <PdfPreview url={url} filename={document.filename} />
}

function DraftTab({ item }: { item: WorkItemDetail }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState('')
  const [content, setContent] = useState('')
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['work-item', item.id] })
  const edit = useMutation({ mutationFn: ({ id, value }: { id: string; value: string }) => api(`/backoffice/work-items/${item.id}/drafts/${id}`, { method: 'PATCH', body: JSON.stringify({ preview_content: value }) }), onSuccess: () => { setEditing(''); refresh() } })
  const regenerate = useMutation({ mutationFn: (id: string) => api(`/backoffice/work-items/${item.id}/drafts/${id}/regenerate`, { method: 'POST' }), onSuccess: refresh })
  return <div className="tab-content"><div className="draft-history-heading"><div><h3>Draft Version History</h3><p>Every regeneration creates a separate reviewable record.</p></div><span>{item.drafts.length} versions</span></div>{item.drafts.length ? [...item.drafts].reverse().map((draft, index) => <section className="panel draft-card" key={draft.id}><PanelTitle title={`${humanize(draft.draft_type)} · Version ${item.drafts.length - index}`} action={<Status value={draft.status} />} />{editing === draft.id ? <textarea className="draft-editor" value={content} onChange={(event) => setContent(event.target.value)} /> : <pre>{draft.preview_content}</pre>}<small>Updated {formatDate(draft.updated_at)}</small><div className="panel-actions">{editing === draft.id ? <><button className="outline-button" onClick={() => setEditing('')}>Cancel</button><button className="primary-button" disabled={!content.trim() || edit.isPending} onClick={() => edit.mutate({ id: draft.id, value: content })}><Check size={14} /> Save Draft</button></> : <><button className="outline-button" disabled={regenerate.isPending} onClick={() => regenerate.mutate(draft.id)}><RefreshCw size={14} /> Regenerate</button><button className="outline-button" disabled={draft.status !== 'drafted'} onClick={() => { setEditing(draft.id); setContent(draft.preview_content) }}><Pencil size={14} /> Edit</button></>}</div></section>) : <EmptyState title="No drafts" body="Drafts produced by the plan will appear here." />}</div>
}

function ApprovalTab({ item, document, extraction }: { item: WorkItemDetail; document?: DocumentSummary; extraction: Extraction | null }) {
  const queryClient = useQueryClient()
  const pending = item.approvals.find((approval) => approval.status === 'pending')
  const [notes, setNotes] = useState('')
  const decision = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api(`/backoffice/approvals/${pending?.id}/${action}`, { method: 'POST', body: JSON.stringify({ notes: notes.trim() || `${humanize(action)} after guided review.` }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); queryClient.invalidateQueries({ queryKey: ['work-item', item.id] }) },
  })
  const latestDecision = [...item.approvals].reverse().find((approval) => approval.status !== 'pending')
  const executed = [...item.activity].reverse().find((event) => ['action_executed','action_failed'].includes(event.event_type))
  const stage = executed ? 4 : latestDecision ? 3 : pending ? 2 : 1
  const signals = exceptionSignals(item, extraction)
  const evidence = extraction?.confidence ?? []
  const validation = extraction?.validation ?? []
  const latestPolicy = item.policy_decisions.at(-1)
  const pendingStep = item.current_plan?.steps.find((candidate) => candidate.id === pending?.action_step_id) ?? item.current_plan?.steps.find((step) => step.requires_approval) ?? item.current_plan?.steps[0]
  const approvalReason = latestPolicy?.reason ?? item.current_plan?.escalation_reason ?? pendingStep?.why_this ?? 'This action can affect document records and needs a reviewer decision before execution.'

  return (
    <div className="reviewer-flow">
      <div className="reviewer-stepper">
        {['Understand','Review Evidence','Decide','Confirm Result'].map((label,index) => <div className={index < stage ? 'complete' : index === stage ? 'active' : ''} key={label}><span>{index < stage ? <Check size={14} /> : index + 1}</span><strong>{label}</strong></div>)}
      </div>

      <section className="panel review-understand">
        <PanelTitle title="1. Why Approval Is Required" action={<Status value={item.status} />} />
        <p>{approvalReason}</p>
        <div className="exception-signal-grid">{signals.map((signal) => <article className={`exception-signal exception-${signal.tone}`} key={signal.label}><AlertTriangle size={15} /><div><strong>{signal.label}</strong><p>{signal.detail}</p></div></article>)}</div>
        <div className="detail-definition-grid">
          <DetailField label="Priority" value={<Priority value={item.priority} />} />
          <DetailField label="Assignee" value={item.assignee} />
          <DetailField label="Requested outcome" value={item.requested_outcome || 'Not provided'} />
          <DetailField label="Source document" value={document?.filename ?? 'No linked document'} />
        </div>
      </section>

      <section className="panel review-evidence">
        <PanelTitle title="Evidence To Check Before Deciding" action={<span className="version">{evidence.length} fields</span>} />
        <div className="evidence-snapshot">
          <DetailField label="Document state" value={<Status value={document?.status ?? 'missing'} />} />
          <DetailField label="Validation findings" value={validation.length} />
          <DetailField label="Field evidence" value={evidence.length} />
          <DetailField label="Plan version" value={item.current_plan ? `${item.current_plan.planner_version} · ${shortId(item.current_plan.id)}` : 'No plan'} />
        </div>
        {validation.length ? <div className="validation-issues compact">{validation.slice(0, 3).map((issue, index) => <article key={index}><AlertTriangle size={14} /><div><strong>{humanize(issue.field_name ?? issue.field ?? 'Document data')}</strong><p>{issue.message ?? 'Validation review required.'}</p></div></article>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No validation findings were returned.</div>}
        <EvidenceExcerpts evidence={evidence} />
      </section>

      <section className="panel review-plan">
        <PanelTitle title="2. Proposed Action" action={item.current_plan ? <Confidence value={item.current_plan.overall_confidence} /> : undefined} />
        {pendingStep ? <article><span>1</span><div><strong>{humanize(pendingStep.action_type)}</strong><p>{pendingStep.why_this || 'This bounded workflow action is waiting for a reviewer decision.'}</p>{pendingStep.why_not ? <small>Not recommended: {pendingStep.why_not}</small> : null}</div><Priority value={pendingStep.risk_level} /></article> : <EmptyState title="No proposed action" body="Generate a plan before making a decision." />}
        <div className="action-meaning-grid">
          <article><CheckCircle2 size={15} /><strong>Approve</strong><p>Allows the proposed action to continue. Use it only after the evidence and risk reason are acceptable.</p></article>
          <article><X size={15} /><strong>Reject</strong><p>Stops this approval request and records why the proposed action should not continue.</p></article>
          <article><Pencil size={15} /><strong>Request Correction</strong><p>Ask for more information from the History tab. It is not a third approval status.</p></article>
        </div>
      </section>

      <section className="panel review-risks">
        <PanelTitle title="Risk Reason" />
        <div className="risk-trigger-list">
          <DetailRow label="Policy risk" value={<Priority value={latestPolicy?.risk_level ?? pendingStep?.risk_level ?? item.priority} />} />
          <DetailRow label="Approval gate" value={item.current_plan?.requires_human || pending ? 'Required' : 'Not required'} />
          <DetailRow label="Business reason" value={approvalReason} />
          <DetailRow label="Escalation reason" value={item.current_plan?.escalation_reason ?? 'No escalation reason recorded'} />
        </div>
      </section>

      <section className="panel review-decision">
        <PanelTitle title="3. Record The Human Decision" />
        {pending ? <><label className="decision-notes"><span>Decision reason</span><textarea value={notes} placeholder="What evidence did you check, and why is this safe or unsafe?" onChange={(event) => setNotes(event.target.value)} /></label><p className="decision-guidance"><FileClock size={14} /> Need more information? Open History and use Request Correction. The approval itself only supports approve or reject.</p><div className="panel-actions"><button className="reject-action" disabled={decision.isPending} onClick={() => decision.mutate('reject')}><X size={15} /> Reject</button><button className="approve-action" disabled={decision.isPending} onClick={() => decision.mutate('approve')}><CheckCircle2 size={15} /> Approve</button></div>{decision.error ? <p className="form-error">{(decision.error as Error).message}</p> : null}</> : latestDecision ? <div className="decision-result"><Status value={latestDecision.status} /><p>{latestDecision.reviewer_notes || 'Decision recorded without notes.'}</p><small>{latestDecision.reviewed_by} · {latestDecision.reviewed_at ? formatDate(latestDecision.reviewed_at) : ''}</small></div> : <p>No approval is required for the current plan.</p>}
      </section>

      <section className="panel review-result">
        <PanelTitle title="4. Confirm Result" />
        {executed ? <div className={`notice ${executed.event_type === 'action_executed' ? 'success' : 'danger'}`}><Activity size={17} /><div><strong>{humanize(executed.event_type)}</strong><p>{executed.summary}</p><small>{executed.actor} · {formatDate(executed.created_at)}</small></div></div> : <div className="notice"><FileClock size={17} /><div><strong>Execution has not completed</strong><p>After approval, execute the approved step from Next Steps. The final audit evidence will appear here.</p></div></div>}
      </section>
    </div>
  )
}

function EvidenceExcerpts({ evidence = [] }: { evidence?: Extraction['confidence'] }) {
  const excerpts = evidence.filter((entry) => entry.source_text).slice(0, 3)
  if (!excerpts.length) return <div className="missing-evidence"><AlertTriangle size={16} /><div><strong>Field-level evidence unavailable</strong><p>Compare the proposal with the linked source before deciding.</p></div></div>
  return (
    <div className="approval-evidence-excerpts">
      {excerpts.map((entry) => <article key={entry.field_name}><strong>{humanize(entry.field_name)}</strong><EvidenceConfidence score={entry.score} /><p>{entry.source_text}</p></article>)}
    </div>
  )
}

function AgentOpsTab({ item }: { item: WorkItemDetail }) {
  const linked = item.activity.filter((event) => event.agent_run_id)
  return <div className="tab-content"><TraceCard item={item} />{linked.length ? <section className="panel"><PanelTitle title="Linked Trace Activity" /><div className="activity-list">{linked.map((event) => <article key={event.id}><span className="activity-dot source-agentops"><Activity size={13} /></span><div><strong>{humanize(event.event_type)}</strong><p>{event.summary}</p><small>Run {shortId(event.agent_run_id!)} · {formatDate(event.created_at)}</small></div><button className="outline-button" onClick={() => window.open(`/ui/agentops?run_id=${event.agent_run_id}`, '_blank')}>Open trace</button></article>)}</div></section> : null}</div>
}

function ActivityTab({ workflow, documentId, loading, error }: { workflow?: DocumentWorkflow; documentId?: string; loading: boolean; error: Error | null }) {
  const queryClient = useQueryClient()
  const [reason, setReason] = useState('')
  const command = useMutation({
    mutationFn: (action: 'retry' | 'request-correction' | 'escalate') => api(`/documents/${documentId}/${action}`, action === 'retry' ? { method: 'POST' } : { method: 'POST', body: JSON.stringify({ reason: reason.trim() || (action === 'escalate' ? 'Manual escalation requested by reviewer.' : 'Please correct the invoice evidence.') }) }),
    onSuccess: () => {
      setReason('')
      queryClient.invalidateQueries({ queryKey: ['document-workflow', documentId] })
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      if (workflow?.work_item?.id) queryClient.invalidateQueries({ queryKey: ['work-item', workflow.work_item.id] })
    },
  })
  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error.message} retry={() => queryClient.invalidateQueries({ queryKey: ['document-workflow', documentId] })} />
  if (!workflow) return <EmptyState title="No workflow activity" body="Link a document to load its durable workflow history." />
  return <div className="activity-tab">
    <section className="workflow-orientation">
      <DetailField label="Current stage" value={humanize(workflow.current_stage)} />
      <DetailField label="Current owner" value={workflow.current_owner} />
      <DetailField label="Waiting for" value={workflow.waiting_for ?? 'Nothing'} />
      <DetailField label="Next action" value={workflow.next_action} />
      {workflow.attention_reason ? <div className="notice warning"><AlertTriangle size={16} /><div><strong>Attention required</strong><p>{workflow.attention_reason}</p></div></div> : null}
    </section>
    <section className="panel workflow-activity">
      <PanelTitle title="Workflow Activity" action={<span className="version">{workflow.activity.length} events</span>} />
      <div className="activity-list">{workflow.activity.map((event) => <article key={event.id}><span className={`activity-dot source-${event.source}`}><Check size={13} /></span><div><strong>{humanize(event.event_type)}</strong><p>{event.summary}</p><small>{event.actor} · {humanize(event.source)} · {formatDate(event.created_at)}</small></div></article>)}</div>
      {!workflow.activity.length ? <EmptyState title="No events recorded" body="Durable workflow events will appear here." /> : null}
    </section>
    <section className="panel recovery-panel">
      <PanelTitle title="Recovery Actions" />
      <p>Use these commands only when the workflow needs intervention. Every action is added to the audit trail.</p>
      {workflow.work_item ? <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason or correction instruction" /> : null}
      <div className="panel-actions">
        {workflow.current_stage === 'failed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('retry')}><RefreshCw size={14} /> Retry Processing</button> : null}
        {workflow.work_item && workflow.current_stage !== 'completed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('request-correction')}><Pencil size={14} /> Request Correction</button> : null}
        {workflow.work_item && workflow.current_stage !== 'completed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('escalate')}><UserRound size={14} /> Escalate</button> : null}
      </div>
      {command.error ? <p className="form-error">{(command.error as Error).message}</p> : null}
    </section>
  </div>
}

function PanelTitle({ title, action }: { title: string; action?: React.ReactNode }) {
  return <div className="panel-title"><h3>{title}</h3>{action}</div>
}
function Meta({ label, value, icon }: { label: string; value: React.ReactNode; icon?: React.ReactNode }) {
  return <div className="meta"><span>{label}</span><strong>{icon}{value}</strong></div>
}
function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="detail-row"><span>{label}</span><strong>{value}</strong></div>
}
function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="detail-field"><span>{label}</span><strong>{value}</strong></div>
}
function Status({ value }: { value: string }) {
  return <span className={`badge status-${value}`}>{humanize(value)}</span>
}
function Priority({ value }: { value: string }) {
  return <span className={`priority priority-${value}`}><i />{humanize(value)}</span>
}
function TypeBadge({ value }: { value: string | null }) {
  return <span className={`type-badge type-${value ?? 'unknown'}`}>{humanize(value ?? 'unclassified')}</span>
}
function Confidence({ value }: { value: string }) {
  return <span className="confidence">{humanize(value)} confidence <CheckCircle2 size={12} /></span>
}
function EvidenceConfidence({ score }: { score: number | null }) {
  const level = score == null ? 'unknown' : score >= .85 ? 'high' : score >= .65 ? 'medium' : 'low'
  return <span className={`confidence confidence-${level}`}>{score == null ? 'Not scored' : `${Math.round(score * 100)}% confidence`}</span>
}
function WorkIcon({ type }: { type: string | null }) {
  const Icon = type?.includes('invoice') ? FileText : type?.includes('vendor') ? Database : type?.includes('accounting') ? FileCheck2 : Zap
  return <span className={`work-icon ${type?.includes('invoice') ? 'red' : type?.includes('vendor') ? 'green' : 'purple'}`}><Icon size={17} /></span>
}
function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="empty-state"><FileText size={24} /><strong>{title}</strong><span>{body}</span></div>
}
function LoadingState() {
  return <div className="loading-state"><Loader2 className="spin" size={20} /> Loading workspace</div>
}
function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  return <main className="error-state"><AlertTriangle size={26} /><h2>Unable to load workspace</h2><p>{message}</p><button className="primary-button" onClick={retry}><RefreshCw size={15} /> Retry</button></main>
}

function queueCounts(items: WorkItemSummary[]) {
  return {
    attention: items.filter((i) => ['high', 'urgent'].includes(i.priority) || ['blocked', 'failed'].includes(i.status)).length,
    progress: items.filter((i) => ['classified', 'planning', 'executing', 'ready_to_execute'].includes(i.status)).length,
    approval: items.filter((i) => i.status === 'awaiting_human').length,
    completed: items.filter((i) => i.status === 'resolved').length,
    blocked: items.filter((i) => ['blocked', 'failed'].includes(i.status)).length,
  }
}
function linkedDocumentForItem(item: WorkItemSummary, documents: DocumentSummary[]) {
  return documents.find((document) => item.linked_document_ids.includes(document.id))
}
function queueDocumentType(item: WorkItemSummary) {
  if (item.work_type?.includes('invoice') || item.work_type?.includes('vendor') || item.work_type?.includes('accounting')) return 'invoice'
  return item.work_type ?? 'document'
}
function queueVendor(item: WorkItemSummary, document?: DocumentSummary) {
  const context = item.business_context
  return context.vendor_name ?? context.vendor ?? context.supplier ?? document?.filename?.replace(/\.[^.]+$/, '') ?? 'Unknown vendor'
}
function queueAmount(item: WorkItemSummary) {
  const context = item.business_context
  const amount = context.total ?? context.total_amount ?? context.amount
  const currencyCode = context.currency ?? ''
  return amount ? `${currencyCode} ${amount}`.trim() : 'Amount unavailable'
}
function matchesFilter(item: WorkItemSummary, filter: QueueFilter) {
  if (filter === 'all') return true
  const counts = { attention: ['high', 'urgent'].includes(item.priority) || ['blocked', 'failed'].includes(item.status), progress: ['classified', 'planning', 'executing', 'ready_to_execute'].includes(item.status), approval: item.status === 'awaiting_human', completed: item.status === 'resolved', blocked: ['blocked', 'failed'].includes(item.status) }
  return counts[filter]
}
function matchesExceptionFilter(item: WorkItemSummary, filter: ExceptionFilter, documents: DocumentSummary[]) {
  if (filter === 'all') return true
  if (filter === 'missing_information') return ['vendor_follow_up', 'insufficient_evidence'].includes(item.work_type ?? '')
  if (filter === 'validation_failure') return item.linked_document_ids.some((id) => documents.find((document) => document.id === id)?.status === 'needs_review')
  if (filter === 'waiting_approval') return item.status === 'awaiting_human'
  if (filter === 'blocked') return item.status === 'blocked'
  return item.status === 'failed'
}
function businessId(item: WorkItemSummary) {
  const prefix = item.work_type?.includes('invoice') ? 'INV' : item.work_type?.includes('accounting') ? 'ACC' : item.work_type?.includes('vendor') ? 'VDR' : 'WRK'
  return `${prefix}-${item.created_at.slice(0, 4)}-${shortId(item.id).toUpperCase()}`
}
function nextAction(status: string) {
  if (status === 'awaiting_human') return 'Review Approval'
  if (status === 'ready_to_execute') return 'Continue Execution'
  if (status === 'blocked') return 'View Blocked Reason'
  if (status === 'resolved') return 'View Result'
  return 'Review Document Task'
}
function invoiceFields(extraction: Extraction | null): [string, string][] {
  const data = extraction?.data ?? {}
  const read = (...keys: string[]) => String(keys.map((key) => data[key]).find((value) => value !== undefined && value !== null) ?? '-')
  return [['Vendor', read('vendor_name', 'vendor')], ['Invoice Number', read('invoice_number')], ['Invoice Date', read('invoice_date')], ['Total Amount', read('total', 'total_amount')], ['Tax Amount', read('tax', 'tax_amount')], ['Currency', read('currency')]]
}
function invoiceLineItems(extraction: Extraction | null): LineItem[] {
  const value = extraction?.data?.line_items
  if (!Array.isArray(value)) return []
  return value.filter((item): item is LineItem => Boolean(item) && typeof item === 'object')
}
function validationSeverity(issues: NonNullable<Extraction['validation']>) {
  const levels = issues.map((issue) => issue.severity?.toLowerCase())
  if (levels.some((level) => ['critical', 'error', 'high'].includes(level ?? ''))) return 'high'
  if (levels.some((level) => ['warning', 'medium'].includes(level ?? ''))) return 'warning'
  return 'warning'
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
function relativeTime(value: string) {
  const minutes = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.round(minutes / 60)}h ago`
  return `${Math.round(minutes / 1440)}d ago`
}
function pageTitle(page: PageId) {
  const titles: Record<PageId, string> = {
    runs: 'Run Traces',
    drafts: 'Drafts',
    approvals: 'Approvals',
    operations: 'Runtime Diagnostics',
    policies: 'Policy Rules',
    guardrails: 'Safety Boundaries',
    integrations: 'Integrations',
    settings: 'Settings',
    reliability: 'System Reliability',
    evaluation: 'Reliability Checks',
    datasets: 'Test Scenarios',
  }
  return titles[page]
}
function intakeTitle(view: IntakeView) {
  return { new: 'New Document', submissions: 'My Documents', invoices: 'Document Library', guide: 'Processing Guide' }[view]
}
function outcomeCopy(workType: string) {
  const copy: Record<string, string> = {
    invoice_review: 'Validate the invoice and prepare it for reviewer approval.',
    accounting_note: 'Prepare a grounded accounting note for operator review.',
    invoice_export: 'Prepare an approved invoice export through controlled execution.',
    vendor_follow_up: 'Prepare a vendor request for missing invoice information.',
  }
  return copy[workType] ?? 'Review the invoice and recommend the next safe action.'
}
function invoiceTitle(workType: string, fields: Record<string, string>) {
  const vendor = fields.vendor_name || 'Incoming Invoice'
  if (workType === 'accounting_note') return `Accounting Note - ${vendor}`
  if (workType === 'invoice_export') return `Invoice Export - ${vendor}`
  if (workType === 'vendor_follow_up') return `Vendor Follow-up - ${vendor}`
  return `Invoice Review - ${vendor}`
}
function attentionReason(item: WorkItemSummary) {
  if (item.status === 'awaiting_human') return 'Waiting for a human approval decision'
  if (item.status === 'blocked') return 'Policy or workflow boundary blocked progress'
  if (item.status === 'failed') return 'Processing or execution failed'
  return 'Human review is required'
}
function decisionRequired(item: WorkItemSummary) {
  if (item.status === 'awaiting_human') return 'Approve, reject, request correction, or escalate.'
  if (item.status === 'blocked') return 'Review the policy reason and choose a safe recovery path.'
  if (item.status === 'failed') return 'Inspect the failure, retry, or transfer ownership.'
  return 'Confirm the evidence and next action.'
}
function exceptionSignals(item: WorkItemSummary, extraction?: Extraction | null) {
  const context = `${item.work_type ?? ''} ${item.tags.join(' ')} ${Object.values(item.business_context).join(' ')}`.toLowerCase()
  const validation = extraction?.validation ?? []
  const messages = validation.map((issue) => `${issue.field_name ?? issue.field ?? ''} ${issue.message ?? ''}`.toLowerCase()).join(' ')
  const signals: Array<{ label: string; detail: string; tone: 'danger' | 'warning' | 'neutral' }> = []
  if (/duplicate/.test(`${context} ${messages}`)) signals.push({ label: 'Duplicate candidate', detail: 'Stored task or validation context indicates a possible duplicate.', tone: 'warning' })
  if (/(total|amount).*(mismatch|does not match)|mismatch.*(total|amount)/.test(messages)) signals.push({ label: 'Total mismatch', detail: 'A deterministic amount validation did not reconcile.', tone: 'danger' })
  if (/vendor.*(mismatch|unknown|missing)|supplier.*(mismatch|unknown|missing)/.test(`${context} ${messages}`)) signals.push({ label: 'Vendor mismatch', detail: 'Vendor identity needs confirmation against source evidence.', tone: 'warning' })
  if (validation.some((issue) => /missing|required|empty|not found/i.test(`${issue.message ?? ''} ${issue.field_name ?? issue.field ?? ''}`))) signals.push({ label: 'Missing field', detail: 'At least one required value was not validated.', tone: 'danger' })
  const lowConfidence = extraction?.confidence?.filter((entry) => entry.score != null && entry.score < .65) ?? []
  if (lowConfidence.length) signals.push({ label: 'Low confidence', detail: `${lowConfidence.length} extracted field${lowConfidence.length === 1 ? '' : 's'} scored below 65%.`, tone: 'warning' })
  if (!extraction?.confidence?.length && item.linked_document_ids.length) signals.push({ label: 'Evidence unavailable', detail: 'No field-level confidence or source excerpts are currently stored.', tone: 'warning' })
  if (item.status === 'awaiting_human') signals.push({ label: 'Approval gated', detail: 'Policy requires a human decision before controlled execution.', tone: 'neutral' })
  if (!signals.length) signals.push({ label: humanize(item.status), detail: attentionReason(item), tone: item.status === 'failed' || item.status === 'blocked' ? 'danger' : 'neutral' })
  return signals
}
function isToday(value: string) {
  const date = new Date(value)
  const now = new Date()
  return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
}
function pageGroup(page: PageId) {
  if (['policies', 'guardrails'].includes(page)) return 'Safety Rules'
  if (['integrations', 'settings'].includes(page)) return 'System Setup'
  if (['reliability', 'evaluation', 'datasets', 'runs', 'operations'].includes(page)) return 'Technical Evidence'
  return 'Daily Work'
}
function percent(value: number | null | undefined) {
  return value === null || value === undefined ? '-' : `${Math.round(value * 100)}%`
}
function decimal(value: number | null | undefined) {
  return value === null || value === undefined ? '-' : value.toFixed(2)
}
function currency(value: number | null | undefined) {
  return value === null || value === undefined ? '-' : `$${value.toFixed(4)}`
}
function humanize(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
function shortId(id: string) {
  return id.slice(0, 8)
}

export default App
