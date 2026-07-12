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
  Loader2,
  Menu,
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
type Screen = { kind: 'overview' } | { kind: 'queue'; filter?: QueueFilter } | { kind: 'workitems' } | { kind: 'detail'; id: string } | { kind: 'documents' } | { kind: 'history' } | { kind: 'page'; page: PageId } | { kind: 'intake'; view: IntakeView }
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
const PRODUCT_NAME = 'Invoice Review'
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
  const [screen, setScreen] = useState<Screen>(() => role === 'intake' ? { kind: 'intake', view: 'new' } : { kind: 'documents' })
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const workspace = useQuery({
    queryKey: ['workspace'],
    queryFn: () => api<Workspace>('/backoffice/workspace'),
    refetchInterval: 10000,
  })
  const goQueue = (filter?: QueueFilter) => setScreen({ kind: 'queue', filter })
  const openItem = (id: string) => setScreen({ kind: 'detail', id })
  const changeRole = (nextRole: UserRole) => {
    localStorage.setItem('docops-role', nextRole)
    setRole(nextRole)
    setScreen(nextRole === 'intake' ? { kind: 'intake', view: 'new' } : { kind: 'documents' })
  }
  const attentionCount = workspace.data?.work_items.filter((item) => ['awaiting_human', 'blocked', 'failed'].includes(item.status)).length ?? 0

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        screen={screen}
        close={() => setSidebarOpen(false)}
        goQueue={goQueue}
        inboxCount={attentionCount}
        role={role}
        goIntake={(view) => setScreen({ kind: 'intake', view })}
        openDocuments={() => setScreen({ kind: 'documents' })}
        openHistory={() => setScreen({ kind: 'history' })}
      />
      <div className="app-main">
        <TopBar
          screen={screen}
          openMenu={() => setSidebarOpen(true)}
          goQueue={goQueue}
          healthy={!workspace.error}
          role={role}
          changeRole={changeRole}
          openItem={openItem}
          openDocuments={() => setScreen({ kind: 'documents' })}
        />
        {workspace.error ? (
          <ErrorState message={(workspace.error as Error).message} retry={() => workspace.refetch()} />
        ) : screen.kind === 'intake' ? (
          screen.view === 'new' ? <GuidedInvoiceWizard onSubmitted={() => setScreen({ kind: 'intake', view: 'invoices' })} onReviewSubmitted={(itemId) => { localStorage.setItem('docops-role', 'administrator'); setRole('administrator'); setScreen({ kind: 'detail', id: itemId }) }} /> : <IntakeLibrary view={screen.view} openItem={openItem} />
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
        ) : screen.kind === 'history' ? (
          <HistoryPage workspace={workspace.data} loading={workspace.isLoading} openItem={openItem} />
        ) : screen.kind === 'page' ? (
          <SectionPage page={screen.page} workspace={workspace.data} loadingWorkspace={workspace.isLoading} openItem={openItem} />
        ) : (
          <QueuePage workspace={workspace.data} loading={workspace.isLoading} openItem={openItem} initialFilter={screen.filter} />
        )}
        <footer className="app-footer">
          <span><ShieldCheck size={14} /> Every upload and decision is saved.</span>
          <span>Local Demo <i /> Data stays on your machine</span>
        </footer>
      </div>
    </div>
  )
}

function Sidebar({
  open,
  screen,
  close,
  goQueue,
  inboxCount,
  role,
  goIntake,
  openDocuments,
  openHistory,
}: {
  open: boolean
  screen: Screen
  close: () => void
  goQueue: () => void
  inboxCount: number
  role: UserRole
  goIntake: (view: IntakeView) => void
  openDocuments: () => void
  openHistory: () => void
}) {
  if (role === 'intake') {
    const intakeItems = [
      [Upload, 'Upload Invoice', () => goIntake('new'), screen.kind === 'intake' && screen.view === 'new'],
      [FileText, 'Invoices', () => goIntake('invoices'), screen.kind === 'intake' && screen.view === 'invoices'],
      [FileClock, 'History', openHistory, screen.kind === 'history'],
    ] as const
    return (
      <>
        {open ? <button className="sidebar-scrim" aria-label="Close menu" onClick={close} /> : null}
        <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
          <div className="brand"><div className="brand-mark"><Sparkles size={23} /></div><div><strong>{PRODUCT_NAME}</strong><span>Intake</span></div></div>
          <nav className="sidebar-nav intake-nav">
            <p className="role-nav-label">INVOICE WORK</p>
            {intakeItems.map(([Icon, label, action, active]) => <button key={label} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => { action(); close() }}><Icon size={19} /><span>{label}</span></button>)}
          </nav>
          <div className="intake-role-card"><UserRound size={18} /><div><span>View</span><strong>Upload invoices</strong></div></div>
        </aside>
      </>
    )
  }

  const reviewerItems = [
    [Upload, 'Upload', () => goIntake('new'), screen.kind === 'intake' && screen.view === 'new', null],
    [FileText, 'Invoices', openDocuments, screen.kind === 'documents', null],
    [ClipboardCheck, 'Approvals', () => goQueue(), screen.kind === 'queue' || screen.kind === 'detail', inboxCount],
    [FileClock, 'History', openHistory, screen.kind === 'history', null],
  ] as const

  return (
    <>
      {open ? <button className="sidebar-scrim" aria-label="Close menu" onClick={close} /> : null}
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Sparkles size={23} /></div>
          <div><strong>{PRODUCT_NAME}</strong><span>Review</span></div>
        </div>
        <nav className="sidebar-nav intake-nav">
          <p className="role-nav-label">INVOICE WORK</p>
          {reviewerItems.map(([Icon, label, action, active, count]) => (
            <button key={label} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => { action(); close() }}>
              <Icon size={19} /><span>{label}</span>{count ? <b>{count}</b> : null}
            </button>
          ))}
        </nav>
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
  openItem,
  openDocuments,
}: {
  screen: Screen
  openMenu: () => void
  goQueue: () => void
  healthy: boolean
  role: UserRole
  changeRole: (role: UserRole) => void
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
          <><h1>Invoice Review</h1><button className="back-link" onClick={goQueue}><ArrowLeft size={14} /> Back to approvals</button></>
        ) : <h1>{screen.kind === 'intake' ? intakeTitle(screen.view) : screen.kind === 'overview' ? 'Dashboard' : screen.kind === 'workitems' ? 'Needs Review' : screen.kind === 'documents' ? 'Invoices' : screen.kind === 'history' ? 'History' : screen.kind === 'page' ? pageTitle(screen.page) : 'Approvals'}</h1>}
      </div>
      <div className="topbar-actions">
        <span className={`health ${healthy ? '' : 'unhealthy'}`}><ShieldCheck size={15} /> {healthy ? 'Online' : 'Offline'}</span>
        {role === 'administrator' ? <div className="notification"><button className="icon-button" aria-label="Notifications" onClick={() => setNotificationsOpen((value) => !value)}><Bell size={18} />{notifications.data?.unread_count ? <b>{notifications.data.unread_count}</b> : null}</button>{notificationsOpen ? <section className="notification-popover"><header><strong>Notifications</strong><button className="outline-button" disabled={!notifications.data?.unread_count || markAll.isPending} onClick={() => markAll.mutate()}>Mark all read</button></header>{notifications.isLoading ? <LoadingState /> : notifications.error ? <p>{notifications.error.message}</p> : notifications.data?.notifications.length ? notifications.data.notifications.map((item) => <button className={item.read_at ? '' : 'unread'} key={item.id} onClick={() => follow(item)}><span className={`activity-dot ${item.severity}`}><Bell size={12} /></span><div><strong>{item.title}</strong><p>{item.message}</p><small>{relativeTime(item.created_at)}</small></div></button>) : <EmptyState title="No notifications" body="Operational events will appear here." />}</section> : null}</div> : null}
        <span className="avatar">W</span>
        <div className="operator"><strong>William Lo</strong><span>{role === 'intake' ? 'Uploader' : 'Reviewer'}</span></div>
        <select className="role-select" value={role} onChange={(event) => changeRole(event.target.value as UserRole)} aria-label="View application as role" title="Demo view only; backend role enforcement is not enabled">
          <option value="intake">Uploader</option>
          <option value="administrator">Reviewer</option>
        </select>
      </div>
    </header>
  )
}

function GuidedInvoiceWizard({ onSubmitted, onReviewSubmitted }: { onSubmitted: () => void; onReviewSubmitted: (itemId: string) => void }) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [documentId, setDocumentId] = useState(() => localStorage.getItem('active-invoice-document') ?? '')
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
      queryClient.invalidateQueries({ queryKey: ['invoice-library'] })
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
        setProcessMessage(status === 'failed' ? 'The app could not read this invoice. Check the PDF and try again.' : 'The invoice is waiting to be read. Try again in a moment.')
      }
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-library'] })
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
      queryClient.invalidateQueries({ queryKey: ['invoice-library'] })
    },
  })
  const reprocessMutation = useMutation({
    mutationFn: () => api(`/documents/${documentId}/reprocess`, { method: 'POST' }),
    onSuccess: async () => {
      await detail.refetch()
      setStep(1)
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-library'] })
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
  const submitMutation = useMutation({
    mutationFn: async () => {
      await api(`/invoices/${documentId}/draft`, { method: 'POST', body: JSON.stringify(draftPayload()) })
      const selected = 'invoice_review'
      const workspace = await api<Workspace>('/backoffice/workspace')
      const existing = workspace.work_items.find((item) => item.linked_document_ids.includes(documentId))
      const created = existing ? { work_item: existing } : await api<{ work_item: WorkItemSummary }>('/backoffice/work-items', { method: 'POST', headers: { 'Idempotency-Key': `invoice-submit:${documentId}:${selected}` }, body: JSON.stringify({ title: invoiceTitle(selected, fields), work_type: selected, linked_document_ids: [documentId], requested_outcome: outcomeCopy(selected) }) })
      if (!existing?.current_plan_id) await api(`/backoffice/work-items/${created.work_item.id}/plan`, { method: 'POST', headers: { 'Idempotency-Key': `invoice-plan:${documentId}:${selected}` }, body: JSON.stringify({ requested_outcome: outcomeCopy(selected) }) })
      return created.work_item
    },
    onSuccess: (item) => {
      localStorage.removeItem('active-invoice-document')
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-library'] })
      setSubmittedItem(item)
      setStep(4)
    },
  })

  const steps = ['Upload', 'Read', 'Check', 'Send']
  const document = detail.data?.document
  const validation = detail.data?.extraction?.validation ?? []
  const arithmeticIssues = invoiceArithmeticIssues(fields, lineItems)
  const duplicate = uploadPolicy.data?.duplicates?.[0]
  const maxBytes = uploadPolicy.data?.max_upload_bytes ?? 15 * 1024 * 1024
  return (
    <main className="guided-page">
      <section className="guided-heading"><div><span>UPLOAD INVOICE</span><h2>Upload and check an invoice</h2><p>Upload a PDF invoice, check the detected fields, then send it for reviewer approval.</p></div><WorkflowOrientation step={steps[Math.min(step, 3)]} owner={step < 3 ? 'You' : 'System'} waiting={step === 0 ? 'Invoice PDF' : undefined} next={step === 0 ? 'Upload invoice' : step === 1 ? 'Read invoice data' : step === 2 ? 'Check detected fields' : 'Send for review'} /></section>
      <div className="wizard-stepper">{steps.map((label, index) => <div className={index < step ? 'complete' : index === step ? 'active' : ''} key={label}><span>{index < step ? <Check size={15} /> : index + 1}</span><strong>{label}</strong></div>)}</div>
      <section className="wizard-card">
        {step === 0 ? <div className="upload-layout"><div className="upload-step"><label className="upload-zone"><Upload size={32} /><strong>{file?.name ?? 'Choose an invoice PDF'}</strong><span>PDF only, up to {formatBytes(maxBytes)}.</span>{file ? <small>{formatBytes(file.size)} - ready to upload</small> : null}<input type="file" accept="application/pdf,.pdf" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setUploadProgress(0) }} /></label>{duplicate ? <div className="duplicate-warning"><AlertTriangle size={16} /><span><strong>Possible duplicate</strong>A file with the same name and size was submitted {formatDate(duplicate.created_at)}.</span></div> : null}{uploadMutation.isPending ? <div className="upload-progress"><span style={{ width: `${uploadProgress}%` }} /><strong>{uploadProgress}% uploaded</strong></div> : null}<button className="primary-button wizard-primary" disabled={!file || file.size > maxBytes || uploadMutation.isPending} onClick={() => uploadMutation.mutate()}>{uploadMutation.isPending ? <Loader2 className="spin" size={17} /> : <Upload size={17} />} Upload Invoice</button>{uploadMutation.error ? <p className="wizard-error">{(uploadMutation.error as Error).message}</p> : null}</div><PdfPreview url={pdfUrl} filename={file?.name ?? ''} /></div> : null}
        {step === 1 ? <div className="extract-step"><StageActivity events={detail.data?.audit_events ?? []} active={processMutation.isPending} /><div className="wizard-actions"><button className="danger-outline-button" disabled={cancelMutation.isPending || !['queued','failed'].includes(document?.status ?? '')} onClick={() => cancelMutation.mutate()}><X size={16} /> Cancel Upload</button><button className="primary-button" disabled={processMutation.isPending || document?.status === 'failed'} onClick={() => { setProcessMessage(''); processMutation.mutate() }}>{processMutation.isPending ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />} Read Invoice Data</button></div>{processMessage ? <p className="wizard-error">{processMessage}</p> : null}{processMutation.error ? <p className="wizard-error">{(processMutation.error as Error).message}</p> : null}{cancelMutation.error ? <p className="wizard-error">{(cancelMutation.error as Error).message}</p> : null}</div> : null}
        {step === 2 ? <div className="verification-layout"><PdfPreview url={pdfUrl} filename={document?.original_filename ?? ''} /><div className="verify-step"><div className="verify-header"><div><Status value={document?.status ?? 'processing'} /><h3>Check invoice data</h3><p>Compare the detected values with the PDF before sending it for review.</p></div><span className="confidence">{detail.data?.extraction?.confidence?.length ?? 0} fields found</span></div><div className="verify-grid">{guidedFields.map(([key, label, type]) => { const evidence = detail.data?.extraction?.confidence?.find((item) => item.field_name === key); return <label key={key}><span>{label}{evidence?.score != null ? <b>{matchCopy(evidence.score)}</b> : null}</span><input type={type} value={fields[key] ?? ''} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} />{evidence?.source_text ? <small title={evidence.source_text}>Page {evidence.source_page ?? 1}: {evidence.source_text}</small> : null}</label> })}</div><LineItemEditor items={lineItems} onChange={setLineItems} />{[...validation.map((issue) => `${issue.field_name ?? issue.field ?? 'Invoice data'}: ${issue.message}`), ...arithmeticIssues].length ? <div className="validation-list">{[...validation.map((issue) => `${issue.field_name ?? issue.field ?? 'Invoice data'}: ${issue.message}`), ...arithmeticIssues].map((message, index) => <p key={index}><AlertTriangle size={14} /><span>{message}</span></p>)}</div> : <div className="validation-ok"><CheckCircle2 size={16} /> Totals look consistent.</div>}<div className="wizard-actions">{['extracted','needs_review'].includes(document?.status ?? '') ? <button className="outline-button" disabled={reprocessMutation.isPending} onClick={() => reprocessMutation.mutate()}><RefreshCw size={15} /> Read Again</button> : null}<button className="primary-button" disabled={arithmeticIssues.length > 0} onClick={() => setStep(3)}><Check size={17} /> Continue</button></div></div></div> : null}
        {step === 3 ? <div className="submit-step"><div className="submit-summary"><WorkIcon type="invoice_review" /><div><span>READY FOR REVIEW</span><h3>{fields.vendor_name || document?.original_filename || 'Invoice'}</h3><p>{fields.invoice_number || shortId(documentId)} - {fields.currency || '-'} {fields.total || '-'}</p></div></div><div className="notice"><FileCheck2 size={17} /><div><strong>Send to reviewer</strong><p>This creates one review item so a reviewer can approve, reject, or ask for correction.</p></div></div><div className="wizard-actions"><button className="outline-button" onClick={() => setStep(2)}>Back</button><button className="primary-button" disabled={submitMutation.isPending} onClick={() => submitMutation.mutate()}>{submitMutation.isPending ? <Loader2 className="spin" size={17} /> : <Play size={17} />} Send for Review</button></div>{submitMutation.error ? <p className="wizard-error">{(submitMutation.error as Error).message}</p> : null}</div> : null}
        {step === 4 ? <div className="submission-success"><CheckCircle2 size={42} /><span>SENT FOR REVIEW</span><h3>Invoice is waiting for approval</h3><p>Reference: <strong>{shortId(documentId)}</strong>. You can review it now or track it from Invoices.</p><div className="success-status"><Status value={submittedItem?.status ?? 'planning'} /><span>Owner<strong>Reviewer</strong></span><span>Next<strong>Review this invoice</strong></span></div><div className="wizard-actions"><button className="outline-button" onClick={() => { setStep(0); setFile(null); setDocumentId(''); setSubmittedItem(null); setFields({}); setLineItems([]) }}><Plus size={16} /> Upload Another Invoice</button><button className="outline-button" onClick={onSubmitted}><FileClock size={16} /> View Invoices</button><button className="primary-button" disabled={!submittedItem?.id} onClick={() => submittedItem?.id && onReviewSubmitted(submittedItem.id)}><ClipboardCheck size={16} /> Review This Invoice</button></div></div> : null}
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
  return <aside className="orientation-panel"><div><span>Owner</span><strong>{owner}</strong></div><div><span>Step</span><strong>{step}</strong></div>{waiting ? <div><span>Needs</span><strong>{waiting}</strong></div> : null}<div className="next"><span>Next</span><strong>{next}</strong></div></aside>
}

function StageActivity({ events, active }: { events: DocumentDetail['audit_events']; active: boolean }) {
  const stages = [{ label: 'PDF received', done: true }, { label: 'Invoice data found', done: !active && events.some((event) => event.event_type === 'processing_succeeded'), active }, { label: 'Basic checks completed', done: !active && events.some((event) => event.event_type === 'processing_succeeded') }]
  return <div className="stage-activity"><h3>{active ? 'Reading invoice data' : 'Ready to read invoice data'}</h3><p>The app will detect key invoice fields and show them for checking.</p>{stages.map((stage) => <div key={stage.label} className={stage.done ? 'done' : stage.active ? 'active' : ''}><span>{stage.done ? <Check size={15} /> : stage.active ? <Loader2 className="spin" size={15} /> : null}</span><strong>{stage.label}</strong></div>)}</div>
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
  const invoices = useQuery({
    queryKey: ['invoice-library', view, search, statusFilter, createdFrom, createdTo, page],
    queryFn: () => api<InvoiceList>(`/invoices?${params}`),
    enabled: view !== 'guide',
  })
  if (view === 'guide') return <main className="guided-page"><section className="guided-heading"><div><span>INVOICE GUIDE</span><h2>How an invoice moves through the app</h2><p>Upload a PDF, check the invoice data, send it to a reviewer, then record the decision.</p></div></section><div className="guide-grid">{['Upload the PDF','Read invoice data','Check fields and warnings','Send for review','Reviewer approves or rejects','Ask for correction when needed','Save the decision history'].map((title,index) => <article key={title}><span>{index + 1}</span><h3>{title}</h3></article>)}</div></main>
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
          <h2>Invoices</h2>
          <p>Every uploaded invoice appears here, including invoices waiting for reviewer approval.</p>
        </div>
      </section>
      <div className="invoice-toolbar">
        <label><Search size={16} /><input value={search} placeholder="Search vendor, file, or invoice number..." onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label>
        <label className="date-filter"><span>From</span><input aria-label="Submitted from" type="date" value={createdFrom} max={createdTo || undefined} onChange={(event) => { setCreatedFrom(event.target.value); setPage(1) }} /></label>
        <label className="date-filter"><span>To</span><input aria-label="Submitted to" type="date" value={createdTo} min={createdFrom || undefined} onChange={(event) => { setCreatedTo(event.target.value); setPage(1) }} /></label>
        <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1) }}>
          <option value="">All statuses</option>
          {['queued','processing','needs_review','awaiting_human','approved','rejected','failed','cancelled','exported'].map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}
        </select>
        {(search || statusFilter || createdFrom || createdTo) ? <button className="outline-button" onClick={resetFilters}><X size={14} /> Clear</button> : null}
      </div>
      <section className="data-panel invoice-card-table">
        {invoices.isLoading ? <LoadingState /> : invoices.data?.items.map((doc) => (
          <button className="invoice-list-card" key={doc.id} onClick={() => setSelectedId(doc.id)}>
            <div className="invoice-review-main">
              <WorkIcon type="invoice_review" />
              <div>
                <span>{shortId(doc.id).toUpperCase()}</span>
                <h3>{doc.vendor_name || doc.original_filename}</h3>
                <p>{doc.original_filename}</p>
              </div>
            </div>
            <div className="invoice-review-meta">
              <span>Amount<strong>{invoiceAmount(doc)}</strong></span>
              <span>Submitted<strong>{formatDate(doc.created_at)}</strong></span>
              <span>Owner<strong>{doc.current_owner}</strong></span>
            </div>
            <div className="invoice-review-status">
              <Status value={doc.status} />
              <small>{invoiceStageCopy(doc.current_stage)}</small>
            </div>
            <span className="primary-button">{doc.work_item_id ? 'Open review' : 'Check status'}</span>
          </button>
        ))}
        {!invoices.isLoading && !invoices.data?.items.length ? <EmptyState title={search || statusFilter || createdFrom || createdTo ? 'No invoices match your filters' : 'No invoices yet'} body={search || statusFilter || createdFrom || createdTo ? 'Clear the filters or search for another vendor, file, or invoice number.' : 'Upload your first invoice, then it will appear here automatically.'} /> : null}
      </section>
      {invoices.data && invoices.data.total_pages > 1 ? <div className="invoice-pagination"><button className="icon-button" disabled={page === 1} onClick={() => setPage((current) => current - 1)}><ChevronLeft size={16} /></button><span>Page {page} of {invoices.data.total_pages} - {invoices.data.total} invoices</span><button className="icon-button" disabled={page === invoices.data.total_pages} onClick={() => setPage((current) => current + 1)}><ChevronRight size={16} /></button></div> : null}
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
          <div className="status-orientation"><div><small>Stage</small><strong>{invoiceStageCopy(data.current_stage)}</strong></div><div><small>Owner</small><strong>{data.current_owner}</strong></div><div><small>Next action</small><strong>{plainNextAction(data.next_action)}</strong></div><Status value={data.document.status} /></div>
          <PdfPreview url={pdfUrl} filename={data.document.original_filename} />
          <section className="status-extraction"><h3>Invoice data</h3><div>{guidedFields.map(([key, label]) => <span key={key}><small>{label}</small><strong>{String(data.extraction?.data?.[key] ?? '-')}</strong></span>)}</div></section>
          {data.extraction?.validation?.length ? <div className="validation-list">{data.extraction.validation.map((issue, index) => <p key={index}><AlertTriangle size={14} /><span>{issue.field_name ?? issue.field}: {issue.message}</span></p>)}</div> : null}
          {data.attention_reason ? <div className="duplicate-warning"><AlertTriangle size={16} /><span><strong>Attention required</strong>{data.attention_reason}</span></div> : null}
          <section className="status-activity"><h3>Recent history</h3>{data.activity.slice(-5).reverse().map((event) => <div key={event.id}><span /><p><strong>{activityLabel(event.event_type)}</strong><small>{event.actor} - {formatDate(event.created_at)}</small></p></div>)}</section>
          {data.work_item ? <section className="escalation-control"><label>Reviewer note<textarea value={escalationReason} placeholder="Explain why another reviewer is needed..." onChange={(event) => setEscalationReason(event.target.value)} /></label><button className="outline-button" disabled={!escalationReason.trim() || escalate.isPending} onClick={() => escalate.mutate()}><AlertTriangle size={15} /> Send to reviewer</button></section> : null}
          {mutationError ? <p className="wizard-error">{(mutationError as Error).message}</p> : null}
          <footer>
            {pdfUrl ? <a className="outline-button" href={pdfUrl} download={data.document.original_filename}><FileText size={15} /> Download PDF</a> : null}
            {data.document.status === 'failed' ? <button className="outline-button" disabled={retry.isPending} onClick={() => retry.mutate()}><RefreshCw size={15} /> Read again</button> : null}
            {['extracted','needs_review','cancelled'].includes(data.document.status) ? <button className="outline-button" disabled={reprocess.isPending} onClick={() => reprocess.mutate()}><RefreshCw size={15} /> Read again</button> : null}
            {['queued','failed'].includes(data.document.status) ? <button className="danger-outline-button" disabled={cancel.isPending} onClick={() => cancel.mutate()}><X size={15} /> Cancel upload</button> : null}
            {data.work_item ? <button className="primary-button" onClick={() => openItem(data.work_item!.id)}><FileClock size={15} /> Review invoice</button> : null}
          </footer>
        </> : <ErrorState message={(workflow.error as Error)?.message ?? 'Invoice unavailable'} retry={() => workflow.refetch()} />}
      </aside>
    </div>
  )
}

function OperationsOverview({ workspace, loading, openItem, goQueue }: { workspace?: Workspace; loading: boolean; openItem: (id: string) => void; goQueue: (filter?: QueueFilter) => void }) {
  const [createOpen, setCreateOpen] = useState(false)
  const items = workspace?.work_items ?? []
  const attention = items.filter((item) => ['awaiting_human','blocked','failed'].includes(item.status))
  const counts = queueCounts(items)
  const executing = items.filter((item) => item.status === 'executing').length
  const completedToday = items.filter((item) => item.status === 'resolved' && isToday(item.updated_at)).length
  const metrics: Array<[string, number | string, React.ReactNode, QueueFilter | undefined]> = [
    ['Needs review', attention.length, <AlertTriangle key="attention" size={18} />, 'attention'],
    ['Waiting decision', counts.approval, <UserRound key="approval" size={18} />, 'approval'],
    ['In progress', executing, <Play key="executing" size={18} />, 'progress'],
    ['Done today', completedToday, <CheckCircle2 key="completed" size={18} />, 'completed'],
  ]
  return <main className="section-page"><section className="section-heading"><div><span className="section-eyebrow">REVIEWER</span><h2>Dashboard</h2><p>Invoices that need review, a decision, or a correction.</p></div><div className="section-actions"><button className="primary-button" onClick={() => goQueue()}>Open Approvals</button></div></section><div className="overview-metrics">{metrics.map(([label,value,icon,filter]) => <button key={label} disabled={!filter} onClick={() => filter && goQueue(filter)}><span>{icon}</span><small>{label}</small><strong>{loading ? '-' : value}</strong><ChevronRight size={15} /></button>)}</div>{!loading && !items.length ? <section className="reviewer-start"><CheckCircle2 size={24} /><div><strong>No approval work yet</strong><p>This is normal in a new demo. Uploaded PDFs appear under Invoices first; this dashboard fills when an invoice needs a reviewer decision.</p></div><button className="outline-button" onClick={() => goQueue()}>Open Approvals</button></section> : null}<section className="data-panel"><DataPanelHeader icon={<Inbox size={17} />} title="Needs Review" count={attention.length} />{loading ? <LoadingState /> : attention.length ? <div className="overview-attention">{attention.map((item) => <button key={item.id} onClick={() => openItem(item.id)}><WorkIcon type={item.work_type} /><span><strong>{item.title}</strong><small>{attentionReason(item)}</small></span><Status value={item.status} /><ChevronRight size={16} /></button>)}</div> : <div className="healthy-empty"><CheckCircle2 size={28} /><div><strong>No invoices need review</strong><p>{items.length ? 'New invoices will appear here when someone needs to check them.' : 'Upload an invoice and send it for review to create a reviewer decision.'}</p></div></div>}</section>{createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}</main>
}

function QueuePage({ workspace, loading, openItem, exceptionMode = false, initialFilter }: { workspace?: Workspace; loading: boolean; openItem: (id: string) => void; exceptionMode?: boolean; initialFilter?: QueueFilter }) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<QueueFilter>(initialFilter ?? 'all')
  const [exceptionFilter, setExceptionFilter] = useState<ExceptionFilter>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(1)
  const pageSize = 8
  const [createOpen, setCreateOpen] = useState(false)
  useEffect(() => { if (initialFilter) setFilter(initialFilter) }, [initialFilter])
  const allItems = workspace?.work_items ?? []
  const exceptionItems = allItems.filter((item) => ['awaiting_human', 'blocked', 'failed'].includes(item.status) || ['vendor_follow_up', 'insufficient_evidence'].includes(item.work_type ?? '') || item.linked_document_ids.some((id) => workspace?.documents.find((document) => document.id === id)?.status === 'needs_review'))
  const items = exceptionMode ? exceptionItems : allItems
  const counts = queueCounts(items)
  const filtered = items.filter((item) => matchesFilter(item, filter) && (!exceptionMode || matchesExceptionFilter(item, exceptionFilter, workspace?.documents ?? [])) && `${item.title} ${item.id} ${item.assignee}`.toLowerCase().includes(search.toLowerCase()))
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize))
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize)
  const emptyCopy = items.length
    ? {
      title: 'No invoices match this view',
      body: 'Clear the search or switch to All.',
      next: 'Invoices still waiting for a decision will remain in Approvals.',
    }
    : {
      title: exceptionMode ? 'No invoices need attention' : 'No invoices waiting for approval',
      body: exceptionMode ? 'Nothing is blocked or waiting for correction right now.' : 'Approvals only shows invoices that need a reviewer decision.',
      next: 'Uploaded PDFs appear under Invoices first. After an invoice is sent for review, it will appear here.',
    }
  useEffect(() => { setPage(1) }, [search, filter, exceptionFilter])
  useEffect(() => { if (page > totalPages) setPage(totalPages) }, [page, totalPages])
  const bulkPriority = useMutation({
    mutationFn: () => Promise.all([...selected].map((id) => api(`/backoffice/work-items/${id}`, { method: 'PATCH', body: JSON.stringify({ priority: 'high' }) }))),
    onSuccess: () => { setSelected(new Set()); queryClient.invalidateQueries({ queryKey: ['workspace'] }) },
  })

  const metrics = [
    ['Invoices', items.length, Inbox, 'blue', 'All review items'],
    ['Needs Review', counts.attention, AlertTriangle, 'red', 'Needs a person'],
    ['In Progress', counts.progress, Play, 'blue', 'Being processed'],
    ['Waiting Decision', counts.approval, UserRound, 'amber', 'Approve or reject'],
    ['Completed Today', counts.completed, ShieldCheck, 'green', 'Finished reviews'],
  ] as const

  return (
    <main className="queue-page">
      <section className="page-heading">
        <div><h2>{exceptionMode ? 'Needs Review' : 'Approvals'}</h2><p>{exceptionMode ? 'Invoices that need review, correction, approval, or recovery.' : 'Invoices waiting for a reviewer decision.'}</p></div>
        <div className="queue-tools">
          <label className="search-box"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search invoices..." /></label>
        </div>
      </section>
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
        {exceptionMode ? <div className="exception-tabs">{([['all','All Exceptions'],['missing_information','Missing Information'],['validation_failure','Validation Failure'],['waiting_approval','Waiting Approval'],['blocked','Blocked'],['failed','Failed']] as [ExceptionFilter,string][]).map(([value,label]) => <button className={exceptionFilter === value ? 'active' : ''} key={value} onClick={() => setExceptionFilter(value)}>{label} <span>{items.filter((item) => matchesExceptionFilter(item, value, workspace?.documents ?? [])).length}</span></button>)}</div> : null}
        <div className="queue-tabs">
          {([
            ['all', `All (${items.length})`],
            ['attention', `Needs Review (${counts.attention})`],
            ['progress', `In Progress (${counts.progress})`],
            ['approval', `Waiting Decision (${counts.approval})`],
            ['completed', `Completed (${counts.completed})`],
          ] as [QueueFilter, string][]).map(([value, label]) => <button className={filter === value ? 'active' : ''} onClick={() => setFilter(value)} key={value}>{label}</button>)}
        </div>
        <WorkItemTable items={paged} documents={workspace?.documents ?? []} loading={loading} openItem={openItem} page={page} totalPages={totalPages} total={filtered.length} setPage={setPage} emptyCopy={emptyCopy} />
      </section>
      {createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}
    </main>
  )
}

function WorkItemTable({ items, documents, loading, openItem, page, totalPages, total, setPage, emptyCopy }: { items: WorkItemSummary[]; documents: DocumentSummary[]; loading: boolean; openItem: (id: string) => void; page: number; totalPages: number; total: number; setPage: (page: number) => void; emptyCopy: { title: string; body: string; next?: string } }) {
  if (loading) return <LoadingState label="Loading invoices" />
  return (
    <div className="invoice-card-list">
      {items.map((item) => {
        const document = linkedDocumentForItem(item, documents)
        return (
          <button className="invoice-review-card" key={item.id} onClick={() => openItem(item.id)}>
            <div className="invoice-review-main">
              <WorkIcon type={item.work_type} />
              <div>
                <span>{businessId(item)}</span>
                <h3>{document?.filename ?? item.title}</h3>
                <p>{queueVendor(item, document)} - {queueAmount(item)}</p>
              </div>
            </div>
            <div className="invoice-review-status">
              <Status value={item.status} />
              <small>{attentionReason(item)}</small>
            </div>
            <div className="invoice-review-meta">
              <span>Owner<strong>{item.assignee}</strong></span>
              <span>Updated<strong>{relativeTime(item.updated_at)}</strong></span>
            </div>
            <span className="primary-button">{nextAction(item.status)}</span>
          </button>
        )
      })}
      {items.length === 0 ? <EmptyState title={emptyCopy.title} body={emptyCopy.body} next={emptyCopy.next} /> : null}
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

  const tabs = ['Check invoice', 'Make decision', 'History']

  return (
    <main className="detail-page">
      <aside className="inbox-rail">
        <div className="rail-title"><h2>Approvals</h2></div>
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
            <button className="outline-button" onClick={() => setEditOpen(true)}><Pencil size={16} /> Edit</button>
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
          <DetailDecisionSummary item={item} document={linkedDocument} openDecision={() => setActiveTab('Make decision')} />
        </header>
        <div className="detail-tabs">
          {tabs.map((tab) => (
            <button className={activeTab === tab ? 'active' : ''} onClick={() => setActiveTab(tab)} key={tab}>{tab}</button>
          ))}
        </div>
        {activeTab === 'Check invoice' ? (
          <WorkspaceTab item={item} document={linkedDocument} extraction={documentDetail.data?.extraction ?? null} loading={documentDetail.isLoading} />
        ) : activeTab === 'Make decision' ? <ApprovalTab item={item} document={linkedDocument} extraction={documentDetail.data?.extraction ?? null} /> :
            activeTab === 'History' ? <ActivityTab workflow={documentWorkflow.data} documentId={linkedDocument?.id} loading={documentWorkflow.isLoading} error={documentWorkflow.error as Error | null} /> :
                <EmptyState title={`${activeTab} timeline`} body="This view is not available for the current workflow." />}
      </section>
      {editOpen ? <EditWorkItemModal item={item} close={() => setEditOpen(false)} /> : null}
      {createOpen ? <CreateWorkItemModal documents={workspace?.documents ?? []} close={() => setCreateOpen(false)} openItem={openItem} /> : null}
    </main>
  )
}

function DetailDecisionSummary({ item, document, openDecision }: { item: WorkItemDetail; document?: DocumentSummary; openDecision: () => void }) {
  const nextStep = item.current_plan?.steps.find((step) => !['completed', 'executed'].includes(step.status)) ?? item.current_plan?.steps[0]
  const pendingApproval = item.approvals.find((approval) => approval.status === 'pending')
  return (
    <section className="decision-summary" aria-label="Work item decision summary">
      <article>
        <span>Needs review because</span>
        <strong>{attentionReason(item)}</strong>
        <p>{decisionRequired(item)}</p>
      </article>
      <article>
        <span>Recommended next step</span>
        <strong>{nextStep ? businessActionLabel(nextStep.action_type) : item.current_plan ? 'No open action' : 'Check invoice first'}</strong>
        <p>{nextStep?.why_this ?? item.requested_outcome ?? 'Check the invoice before taking action.'}</p>
      </article>
      <article>
        <span>Reviewer decision</span>
        <strong>{pendingApproval ? 'Decision pending' : item.current_plan?.requires_human ? 'Reviewer check required' : 'No decision needed'}</strong>
        <p>{pendingApproval ? 'Approve, reject, or ask for correction.' : item.current_plan?.requires_human ? 'Check the invoice before continuing.' : 'Continue from the next available action.'}</p>
        <button className="inline-decision-button" onClick={openDecision}>Go to decision</button>
      </article>
      <article>
        <span>Invoice PDF</span>
        <strong>{document?.filename ?? 'No PDF linked'}</strong>
        <p>{document ? `Invoice status: ${statusLabel(document.status)}.` : 'Link an invoice PDF before making a final decision.'}</p>
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

function WorkspaceTab({ item, document, extraction, loading }: { item: WorkItemDetail; document?: DocumentSummary; extraction: Extraction | null; loading: boolean }) {
  const fields = invoiceFields(extraction)
  const issues = extraction?.validation ?? []
  const evidence = extraction?.confidence ?? []
  const lineItems = invoiceLineItems(extraction)

  return (
    <div className="document-workspace">
      <section className={`workspace-alert ${issues.length ? 'has-issues' : evidence.length ? 'clear' : 'missing'}`}>
        {issues.length ? <AlertTriangle size={18} /> : evidence.length ? <CheckCircle2 size={18} /> : <FileClock size={18} />}
        <div><strong>{issues.length ? `${issues.length} issue${issues.length === 1 ? ' needs' : 's need'} review` : evidence.length ? 'Invoice data is ready to check' : 'Invoice data needs manual checking'}</strong><p>{issues.length ? 'Fix or reject the invoice before approving it.' : evidence.length ? `${evidence.length} fields were found in the PDF.` : 'The app could not show PDF snippets for this invoice.'}</p></div>
        <Priority value={item.priority} />
      </section>

      <div className="workspace-primary">
        <section className="workspace-preview">
          <div className="workspace-section-heading"><div><span>Invoice PDF</span><h3>{document?.filename ?? 'No linked document'}</h3></div>{document ? <Status value={document.status} /> : null}</div>
          {loading ? <LoadingState label="Loading invoice PDF" /> : document ? <AuthenticatedPdfPreview document={document} /> : <EmptyState title="No invoice preview" body="Link an invoice PDF before reviewing or approving this item." next="Without a PDF, compare the invoice information manually before deciding." />}
        </section>

        <div className="workspace-review">
          <section className="panel workspace-fields">
            <PanelTitle title="Invoice Fields" action={<TypeBadge value="invoice" />} />
            <p className="workspace-context">Check these values against the PDF before deciding.</p>
            <div className="invoice-fields">{fields.map(([label, value]) => <div className={value === '-' ? 'field-missing' : ''} key={label}><span>{label}</span><strong>{value}</strong><small><i /> {value === '-' ? 'Missing' : 'Detected'}</small></div>)}</div>
          </section>

          <section className="panel workspace-validation">
            <PanelTitle title="Checks" action={<span className={`severity-badge severity-${issues.length ? validationSeverity(issues) : 'clear'}`}>{issues.length ? humanize(validationSeverity(issues)) : 'Passed'}</span>} />
            {issues.length ? <div className="validation-issues">{issues.map((issue, index) => <article key={`${issue.field_name ?? issue.field}-${index}`}><AlertTriangle size={15} /><div><strong>{humanize(issue.field_name ?? issue.field ?? 'Invoice data')}</strong><p>{issue.message ?? 'This needs review.'}</p></div><span className={`severity-badge severity-${issue.severity ?? 'warning'}`}>{humanize(issue.severity ?? 'warning')}</span></article>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No blockers found.</div>}
          </section>

          <section className="panel workspace-line-items">
            <PanelTitle title="Line Items" action={<span className="version">{lineItems.length} items</span>} />
            {lineItems.length ? <div className="line-items-table"><div><strong>Description</strong><strong>Qty</strong><strong>Unit price</strong><strong>Amount</strong></div>{lineItems.map((line, index) => <div key={index}><span>{line.description || '-'}</span><span>{line.quantity || '-'}</span><span>{line.unit_price || '-'}</span><strong>{line.amount || '-'}</strong></div>)}</div> : <EmptyState title="No line items found" body="The app did not find invoice line-item data." next="Open the PDF and check whether line items exist before approving." />}
          </section>

          <section className="panel workspace-evidence">
            <PanelTitle title="PDF Snippets" action={<span className="version">{evidence.length} fields</span>} />
            {evidence.length ? <div className="evidence-list">{evidence.map((entry) => <article className={!entry.source_text ? 'evidence-missing' : ''} key={entry.field_name}><strong>{humanize(entry.field_name)}</strong><EvidenceConfidence score={entry.score} /><p>{entry.source_text || 'No PDF snippet stored for this field. Compare this value with the PDF before deciding.'}</p><small>{entry.source_page ? `PDF page ${entry.source_page}` : 'PDF page not recorded'}</small></article>)}</div> : <div className="missing-evidence"><AlertTriangle size={17} /><div><strong>No PDF snippets available</strong><p>The app did not store snippets for these fields. Compare the values with the PDF before approving, rejecting, or exporting.</p></div></div>}
          </section>
        </div>
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
        {documents.length ? documents.map((document) => <div key={document.id}><WorkIcon type="invoice_review" /><span><strong>{document.filename}</strong><small>{shortId(document.id)} - {formatDate(document.created_at)}</small><SchemaMeta document={document} extraction={null} compact /></span><Status value={document.status} /></div>) : <EmptyState title="No invoice PDF linked" body="This review item was created without an invoice PDF." />}
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
  return <div className="modal-backdrop" role="presentation" onMouseDown={close}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="edit-work-item-title" onMouseDown={(event) => event.stopPropagation()}><header><div><h2 id="edit-work-item-title">Edit Review</h2><p>Update owner and review notes.</p></div><button className="icon-button" aria-label="Close dialog" onClick={close}><X size={18} /></button></header><label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Priority<select value={priority} onChange={(event) => setPriority(event.target.value)}>{['low','normal','high','urgent'].map((value) => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Assignee<input value={assignee} placeholder="Reviewer name or team" onChange={(event) => setAssignee(event.target.value)} /></label><label>Goal<textarea value={outcome} onChange={(event) => setOutcome(event.target.value)} /></label><label>Tags<input value={tags} placeholder="invoice, high-value, vendor" onChange={(event) => setTags(event.target.value)} /></label>{mutation.error ? <p className="form-error">{(mutation.error as Error).message}</p> : null}<footer><button className="outline-button" onClick={close}>Cancel</button><button className="primary-button" disabled={!title.trim() || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? <Loader2 className="spin" size={15} /> : <Check size={15} />} Save Changes</button></footer></section></div>
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
    runs: 'See what the AI tried, what evidence it used, and whether the result passed review checks.',
    drafts: 'Review AI-generated accounting notes, messages, and export previews.',
    approvals: 'Resolve the human decisions blocking controlled execution.',
    operations: 'Inspect worker failures, controlled retries, and authorized audit evidence.',
    policies: 'See the backend rules that decide whether a document action is allowed.',
    guardrails: 'Monitor the safety boundaries enforced across document work.',
    integrations: 'Manage the systems this document workflow can read from or write to.',
    settings: 'Configure this local workspace and its operator access.',
    reliability: 'Review the local evidence used to judge quality, safety, handoffs, and known weak spots.',
    evaluation: 'Check stored runs and plans against repeatable expected outcomes.',
    datasets: 'Inspect the versioned test scenarios behind the reliability checks.',
  }
  return <section className="section-heading"><div><span className="section-eyebrow">{pageGroup(page)}</span><h2>{pageTitle(page)}</h2><p>{copy[page]}</p></div><button className="outline-button" onClick={() => queryClient.invalidateQueries()}><RefreshCw size={15} /> Refresh data</button></section>
}

function RunsPage({ runs }: { runs: AgentRun[] }) {
  const [selected, setSelected] = useState<string | null>(runs[0]?.id ?? null)
  const current = runs.find((run) => run.id === selected) ?? runs[0]
  return <div className="split-page"><section className="data-panel"><DataPanelHeader icon={<Activity size={17} />} title="Recent AI Work" count={runs.length} /><div className="run-list">{runs.map((run) => <button className={current?.id === run.id ? 'active' : ''} key={run.id} onClick={() => setSelected(run.id)}><span className={`run-dot ${run.evaluation.successful_completion ? 'success' : 'warning'}`} /><div><strong>{humanize(run.intent)}</strong><p>{run.request}</p><small>{formatDate(run.created_at)} Â· {run.prompt_version}</small></div><Status value={run.evaluation.successful_completion ? 'resolved' : run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></button>)}</div>{runs.length === 0 ? <EmptyState title="No AI work recorded yet" body="Run a document workflow or reliability check to create trace evidence." next="Start from Work Queue or Reliability Checks after at least one document task exists." /> : null}</section><section className="data-panel run-detail"><DataPanelHeader icon={<Workflow size={17} />} title="Decision Trace" />{current ? <><div className="run-hero"><span className="work-icon purple"><BotIcon /></span><div><span>Run {shortId(current.id)}</span><h3>{humanize(current.intent)}</h3><p>{current.evaluation.decision_reason}</p></div></div><div className="stats-grid compact"><Stat label="Confidence" value={`${Math.round(current.evaluation.confidence_score * 100)}%`} /><Stat label="Tool calls" value={current.evaluation.tool_call_count} /><Stat label="Cost" value={currency(current.evaluation.estimated_cost_usd)} /><Stat label="Blocked actions" value={current.evaluation.blocked_action_count} /></div><div className="trace-comparison"><TraceValue label="Expected action" value={current.evaluation.expected_tool ?? 'Not scored'} /><ChevronRight size={16} /><TraceValue label="Actual action" value={current.evaluation.selected_tool ?? 'No action'} /></div>{current.evaluation.failure_type ? <div className="notice danger"><AlertTriangle size={16} /><div><strong>{humanize(current.evaluation.failure_type)}</strong><p>This run is listed as a known weak spot in the local reliability evidence.</p></div></div> : <div className="notice success"><CheckCircle2 size={16} /><div><strong>Trace passed reliability checks</strong><p>No known weak spot was recorded for this run.</p></div></div>}</> : <EmptyState title="Select a run" body="Decision trace and evaluation evidence will appear here." next="Choose a run from the left after trace data exists." />}</section></div>
}

function DraftsPage({ items, openItem }: { items: WorkItemDetail[]; openItem: (id: string) => void }) {
  const drafts = items.flatMap((item) => item.drafts.map((draft) => ({ draft, item })))
  return <section className="data-panel"><DataPanelHeader icon={<FileClock size={17} />} title="Draft Library" count={drafts.length} /><div className="artifact-grid">{drafts.map(({ draft, item }) => <article className="artifact-card" key={draft.id}><header><span className="work-icon purple"><FileText size={16} /></span><div><TypeBadge value={item.work_type} /><h3>{humanize(draft.draft_type)}</h3></div><Status value={draft.status} /></header><pre>{draft.preview_content}</pre><footer><span>{formatDate(draft.created_at)}</span><button className="outline-button" onClick={() => openItem(item.id)}>Open work item <ChevronRight size={14} /></button></footer></article>)}</div>{drafts.length === 0 ? <EmptyState title="No drafts available" body="Generate a plan containing a draft action." /> : null}</section>
}

function ApprovalsPage({ items, openItem }: { items: WorkItemDetail[]; openItem: (id: string) => void }) {
  const approvals = items.flatMap((item) => item.approvals.map((approval) => ({ approval, item })))
  const pending = approvals.filter(({ approval }) => approval.status === 'pending').length
  const highRisk = approvals.filter(({ item }) => ['high', 'urgent'].includes(item.priority)).length
  return <><div className="approval-summary"><Stat label="Pending decisions" value={pending} icon={<FileClock size={18} />} /><Stat label="High-risk gates" value={highRisk} icon={<ShieldCheck size={18} />} /><Stat label="Decisions recorded" value={approvals.length - pending} icon={<ClipboardCheck size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<ClipboardCheck size={17} />} title="Human Approval Inbox" count={approvals.length} /><div className="approval-table enhanced">{approvals.map(({ approval, item }) => { const signals = exceptionSignals(item); const step = item.current_plan?.steps.find((candidate) => candidate.id === approval.action_step_id); return <article key={approval.id}><span className={`approval-icon ${approval.status}`}><ClipboardCheck size={17} /></span><div><h3>{item.title}</h3><p>{businessId(item)} Â· {signals[0]?.label ?? 'Policy approval gate'}</p><div className="exception-chip-row">{signals.slice(0, 2).map((signal) => <span className={`exception-chip exception-${signal.tone}`} key={signal.label}>{signal.label}</span>)}</div></div><div className="approval-proposal"><small>Proposed action</small><strong>{humanize(step?.action_type ?? 'Awaiting plan')}</strong></div><Priority value={step?.risk_level ?? item.priority} /><Status value={approval.status} /><span>{formatDate(approval.created_at)}</span><button className="outline-button" onClick={() => openItem(item.id)}>Review decision <ChevronRight size={14} /></button></article> })}</div>{approvals.length === 0 ? <EmptyState title="Approval inbox is clear" body="New human gates will appear here when a plan requests confirmation." /> : null}</section></>
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
  return <><div className="stats-grid"><Stat label="Worker status" value={humanize(data?.worker.status ?? 'checking')} icon={<CircleGauge size={18} />} /><Stat label="Queued jobs" value={data?.worker.queued_jobs ?? 0} icon={<FileClock size={18} />} /><Stat label="Failed jobs" value={data?.worker.failed_jobs ?? 0} icon={<AlertTriangle size={18} />} /><Stat label="Stalled jobs" value={data?.worker.stalled_jobs ?? 0} icon={<Activity size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Worker Health" /><div className={`notice ${data?.worker.status === 'degraded' ? 'danger' : 'success'}`}><ShieldCheck size={16} /><div><strong>{humanize(data?.worker.status ?? 'checking')}</strong><p>{data?.worker.evidence}</p></div></div><div className="panel-actions"><button className="outline-button" onClick={downloadAudit}><FileText size={14} /> Export audit CSV</button></div></section><section className="data-panel"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Failed And Dead-Letter Jobs" count={data?.failed_jobs.length ?? 0} /><div className="approval-table">{data?.failed_jobs.map((job) => <article key={job.id}><span className="approval-icon rejected"><AlertTriangle size={17} /></span><div><h3>Document {shortId(job.document_id)}</h3><p>{job.error_message || 'Persistent processing failure.'}</p></div><Status value={job.status} /><span>{job.provider_name ?? 'unknown provider'} Â· {job.attempt_count} attempts</span><button className="outline-button" disabled={retry.isPending} onClick={() => retry.mutate(job.id)}><RefreshCw size={14} /> Retry</button></article>)}</div>{!data?.failed_jobs.length ? <EmptyState title="No failed jobs" body="Worker failures and dead-letter jobs will remain visible here until resolved." /> : null}</section>{toast ? <div className={`app-toast ${toast.kind}`} role="status"><span>{toast.kind === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}</span><p>{toast.message}</p><button onClick={() => setToast(null)}><X size={14} /></button></div> : null}</>
}

function PoliciesPage({ items }: { items: WorkItemDetail[] }) {
  const decisions = items.flatMap((item) => item.policy_decisions.map((decision) => ({ decision, item })))
  const allowed = decisions.filter(({ decision }) => decision.allowed).length
  return <><div className="stats-grid"><Stat label="Policy decisions" value={decisions.length} icon={<FileCheck2 size={18} />} /><Stat label="Allowed actions" value={allowed} icon={<CheckCircle2 size={18} />} /><Stat label="Confirmation gates" value={decisions.filter(({ decision }) => decision.requires_confirmation).length} icon={<UserRound size={18} />} /><Stat label="Blocked actions" value={decisions.length - allowed} icon={<ShieldCheck size={18} />} /></div><section className="data-panel"><DataPanelHeader icon={<FileCheck2 size={17} />} title="Policy Decision Log" count={decisions.length} /><div className="policy-list">{decisions.map(({ decision, item }) => <article key={decision.id}><div className="policy-main"><span className={`policy-result ${decision.allowed ? 'allowed' : 'blocked'}`}>{decision.allowed ? <Check size={15} /> : <X size={15} />}</span><div><h3>{humanize(decision.action_type)}</h3><p>{decision.reason}</p><small>{item.title} Â· {formatDate(item.updated_at)}</small></div></div><div className="policy-tags"><Priority value={decision.risk_level} /><span className="type-badge">{humanize(decision.autonomy_level)}</span>{decision.requires_confirmation ? <Status value="awaiting_human" /> : <Status value="approved" />}</div></article>)}</div></section></>
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
  return <div className="settings-layout"><section className="data-panel settings-panel"><DataPanelHeader icon={<Settings size={17} />} title="Workspace Configuration" /><label><span>Workspace</span><input value={workspace?.workspace_id ?? 'default'} disabled /></label><DetailRow label="Authentication" value="Opaque HttpOnly server session" /><DetailRow label="Credential storage" value="Server-side only; no browser token" /><label><span>Backend endpoint</span><input value="Same origin" disabled /></label><label><span>Frontend endpoint</span><input value={window.location.origin} disabled /></label><div className="settings-actions"><button className="primary-button" onClick={refresh}><RefreshCw size={15} /> Refresh configuration</button>{saved ? <span><CheckCircle2 size={14} /> Refreshed</span> : null}</div></section><section className="data-panel settings-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Runtime And Providers" /><div className="mode-banner"><strong>Production-shaped runtime</strong><p>Secrets stay in the server-side .env file and are never returned to this browser.</p></div>{providers.data?.providers.map((provider) => <DetailRow key={provider.role} label={`${humanize(provider.role)} provider`} value={`${provider.provider_name} Â· ${humanize(provider.status)}`} />)}{integrations.data?.integrations.map((integration) => <DetailRow key={integration.name} label={humanize(integration.name)} value={`${integration.provider} Â· ${humanize(integration.status)}`} />)}<DetailRow label="Fallback state" value={providers.data?.overall_status === 'healthy' ? 'Local deterministic providers active' : 'Real provider configured; mock remains available via .env'} /><DetailRow label="Telemetry" value="Durable local AgentOps" /></section></div>
}

function ReliabilityPage({ summary, runs, regression, promptVersions }: { summary?: ReliabilitySummary; runs: AgentRun[]; regression?: Regression; promptVersions: PromptVersionMetric[] }) {
  const metrics = [
    ['Action Match Rate', percent(summary?.tool_selection_accuracy), 'Expected vs actual actions'],
    ['Unsafe Action Prevention', percent(summary?.unsafe_action_prevention_rate), 'Blocked unsafe attempts'],
    ['Successful Completion', percent(summary?.successful_completion_rate), 'Runs completing safely'],
    ['Human Handoff Rate', percent(summary?.escalation_rate), 'Runs sent to a human'],
  ]
  const enoughObservations = (summary?.total_runs ?? 0) >= 5
  const failedRuns = runs.filter((run) => run.evaluation.failure_type || !run.evaluation.successful_completion)
  return <>
    <EvidenceScope title="Local reliability evidence" detail={`Metrics below come from ${summary?.total_runs ?? 0} stored local run${(summary?.total_runs ?? 0) === 1 ? '' : 's'}. They are useful for this demo workflow, not a production telemetry or general model-quality claim.`} />
    <div className="reliability-metrics">{metrics.map(([label, value, note]) => <article key={label}><div className="ring"><span>{value}</span></div><div><h3>{label}</h3><p>{note}</p></div></article>)}</div>
    <div className="analytics-grid">
      <section className="data-panel"><DataPanelHeader icon={<Activity size={17} />} title="Recent Document Work" /><div className="signal-list">{runs.slice(0, 8).map((run) => <div key={run.id}><span className={`run-dot ${run.evaluation.successful_completion ? 'success' : 'warning'}`} /><strong>{humanize(run.intent)}</strong><span>{Math.round(run.evaluation.confidence_score * 100)}% confidence</span><Status value={run.evaluation.successful_completion ? 'resolved' : run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></div>)}</div>{runs.length === 0 ? <EmptyState title="No reliability signals yet" body="Create document work or run checks to populate this page." next="Upload an invoice, process it, then run Reliability Checks to build evidence." /> : null}</section>
      <section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Operational Efficiency" /><div className="large-stat"><span>Average confidence</span><strong>{percent(summary?.average_confidence)}</strong></div><DetailRow label="Evaluated runs" value={summary?.evaluated_runs ?? 0} /><DetailRow label="Average tool calls" value={decimal(summary?.average_tool_calls_per_task)} /><DetailRow label="Average latency" value={`${decimal(summary?.average_latency_ms)} ms`} /><DetailRow label="Estimated cost / run" value={currency(summary?.estimated_cost_per_run)} /></section>
      <section className="data-panel"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Error Trend" />{enoughObservations ? <div className="failure-bars">{(summary?.failure_trend ?? []).map(({ failure_type, count }) => <div key={failure_type}><span>{humanize(failure_type)}</span><i><b style={{ width: `${Math.min(100, count * 20)}%` }} /></i><strong>{count}</strong></div>)}</div> : <EmptyState title="Not enough observations" body="At least five runs are required before showing an error trend." />}</section>
      <section className="data-panel"><DataPanelHeader icon={<CircleGauge size={17} />} title="Confidence Calibration" />{enoughObservations ? <div className="failure-bars">{Object.entries(summary?.confidence_distribution ?? {}).map(([name, count]) => <div key={name}><span>{humanize(name)}</span><i><b style={{ width: `${Math.min(100, count / Math.max(summary?.total_runs ?? 1, 1) * 100)}%` }} /></i><strong>{count}</strong></div>)}</div> : <EmptyState title="Calibration pending" body="Confidence distribution appears after five observed runs." />}</section>
      <section className="data-panel"><DataPanelHeader icon={<Workflow size={17} />} title="Planning Version Evidence" />{promptVersions.map((version) => <div className="trace-comparison" key={version.prompt_version}><TraceValue label="Version" value={version.prompt_version} /><TraceValue label="Runs" value={String(version.total_runs)} /><TraceValue label="Action match" value={percent(version.tool_selection_accuracy)} /></div>)}</section>
      <section className="data-panel"><DataPanelHeader icon={<Columns3 size={17} />} title="Regression Comparison" />{regression?.deltas.map((delta) => <div className="trace-comparison" key={delta.metric}><TraceValue label="Metric" value={delta.metric} /><TraceValue label="Previous" value={percent(delta.previous)} /><TraceValue label="Current" value={percent(delta.current)} /><Status value={delta.regressed ? 'failed' : 'approved'} /></div>)}{!regression?.deltas.length ? <EmptyState title="No comparison window" body="More runs are needed to compare current and previous windows." /> : null}</section>
      <section className="data-panel known-failures"><DataPanelHeader icon={<AlertTriangle size={17} />} title="Known Weak Spots" count={failedRuns.length} />{failedRuns.slice(0, 6).map((run) => <article key={run.id}><span className="approval-icon rejected"><AlertTriangle size={15} /></span><div><strong>{humanize(run.evaluation.failure_type ?? 'Incomplete run')}</strong><p>{run.evaluation.decision_reason}</p><small>{humanize(run.intent)} Â· Run {shortId(run.id)} Â· {formatDate(run.created_at)}</small></div><Status value={run.evaluation.human_escalated ? 'awaiting_human' : 'failed'} /></article>)}{!failedRuns.length ? <EmptyState title="No weak spots in this sample" body="This only describes the stored local observation set." /> : null}</section>
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
    ? runs.map((run) => ({ id: run.id, label: `${humanize(run.intent)} Â· ${shortId(run.id)}` }))
    : items.filter((item) => item.current_plan).map((item) => ({ id: item.id, label: `${item.title} Â· ${shortId(item.current_plan!.id)}` }))
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
    <EvidenceScope title="Repeatable reliability checks" detail="Each result compares one stored plan or run with a versioned expected outcome. Passing a case does not imply broad document or production coverage." />
    <div className="stats-grid"><Stat label="AI action checks" value={agent?.scenario_count ?? 0} icon={<BotIcon />} /><Stat label="Document workflow checks" value={backoffice?.scenario_count ?? 0} icon={<Workflow size={18} />} /><Stat label="Observed runs" value={runs.length} icon={<Activity size={18} />} /><Stat label="Check mode" value="Repeatable" icon={<CheckCircle2 size={18} />} /></div>
    <div className="evaluation-result-strip"><strong>{completedResults.length ? `${passedResults} of ${completedResults.length} checked cases passed` : 'No cases checked yet'}</strong><span>Results are saved against scenario IDs and versioned test sets.</span>{completedResults.some((result) => result.actual_document_type || result.actual_operation_type) ? <div className="scenario-tags">{completedResults.map((result, index) => <span key={index}>{[result.actual_document_type && `Actual document: ${humanize(result.actual_document_type)}`, result.actual_operation_type && `Actual operation: ${humanize(result.actual_operation_type)}`].filter(Boolean).join(' Â· ')}</span>)}</div> : null}</div>
    <section className="data-panel">
      <div className="evaluation-toolbar">
        <div className="segment-control"><button className={tab === 'backoffice' ? 'active' : ''} onClick={() => setTab('backoffice')}>Document workflow</button><button className={tab === 'agent' ? 'active' : ''} onClick={() => setTab('agent')}>AI tool use</button></div>
        <select value={selectedTarget} onChange={(event) => setTargetId(event.target.value)} aria-label="Evaluation target">{targets.length ? targets.map((target) => <option value={target.id} key={target.id}>{target.label}</option>) : <option value="">No compatible observations</option>}</select>
        <span>{dataset?.dataset_id} Â· {dataset?.dataset_version}</span>
      </div>
      <div className="scenario-list">{dataset?.scenarios.map((scenario, index) => {
        const result = results[scenario.id]
        return <article key={scenario.id}><span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><div><h3>{scenario.title ?? humanize(scenario.id)}</h3><p>{scenario.message ?? `${humanize(scenario.work_type ?? 'backoffice')} scenario with deterministic plan expectations.`}</p><div className="scenario-tags">{scenario.document_type ? <span>Document: {humanize(scenario.document_type)}</span> : null}{scenario.operation_type ? <span>Operation: {humanize(scenario.operation_type)}</span> : null}{scenario.expected_tool ? <span>Tool: {humanize(scenario.expected_tool)}</span> : null}{scenario.expected_risk ? <span>Risk: {humanize(scenario.expected_risk)}</span> : null}{scenario.expected_confidence ? <span>Confidence: {scenario.expected_confidence}</span> : null}{result ? <Status value={result.passed ? 'approved' : 'failed'} /> : null}</div>{result ? <small>{Object.entries(result.checks).map(([name, passed]) => `${humanize(name)}: ${passed ? 'pass' : 'fail'}`).join(' Â· ')}</small> : null}<ScenarioResultEvidence scenario={scenario} result={result} /></div><button className="outline-button" disabled={!selectedTarget || evaluation.isPending} onClick={() => evaluation.mutate({ scenarioId: scenario.id })}>{evaluation.isPending ? <Loader2 size={14} /> : <Play size={14} />} Evaluate</button></article>
      })}</div>
      {evaluation.error ? <div className="notice danger"><AlertTriangle size={16} /><p>{evaluation.error.message}</p></div> : null}
    </section>
  </>
}

function DatasetsPage({ agent, backoffice }: { agent?: ScenarioDataset; backoffice?: ScenarioDataset }) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  return <><EvidenceScope title="Versioned local test scenarios" detail="These test sets define repeatable expectations for the implemented invoice workflow and AI tool use. They are fixtures, not customer documents." /><div className="dataset-grid">{[agent, backoffice].filter(Boolean).map((dataset) => {
    const selected = dataset!.scenarios.find((scenario) => scenario.id === scenarioId)
    return <section className="dataset-card" key={dataset!.dataset_id}><header><span className="dataset-icon"><Database size={22} /></span><div><span>VERSIONED TEST SET</span><h3>{humanize(dataset!.dataset_id)}</h3></div><Status value="approved" /></header><p>{dataset!.description}</p><div className="dataset-meta"><div><span>Current version</span><strong>{dataset!.dataset_version}</strong></div><div><span>Version history</span><strong>{dataset!.dataset_version} (current)</strong></div><div><span>Scenarios</span><strong>{dataset!.scenario_count}</strong></div></div><div className="dataset-preview">{dataset!.scenarios.map((scenario) => <button key={scenario.id} onClick={() => setScenarioId(scenario.id)}><FileText size={14} /><span>{scenario.title ?? scenario.message ?? humanize(scenario.id)}</span><ChevronRight size={14} /></button>)}</div>{selected ? <div className="notice"><FileText size={16} /><div><strong>{selected.title ?? humanize(selected.id)}</strong><p>{selected.message ?? `Expected workflow: ${selected.expected_plan_steps?.map(humanize).join(' -> ') ?? humanize(selected.work_type ?? 'AI tool scenario')}`}</p><ScenarioMetaTags scenario={selected} /><small>Scenario ID: {selected.id}</small></div></div> : null}{expanded === dataset!.dataset_id ? <div className="dataset-preview"><strong>Required scenario fields</strong>{(dataset!.required_fields ?? Object.keys(dataset!.scenarios[0] ?? {})).map((field) => <div key={field}><Check size={14} /><span>{field}</span></div>)}</div> : null}<footer><button className="outline-button" onClick={() => setExpanded(expanded === dataset!.dataset_id ? null : dataset!.dataset_id)}><FileText size={14} /> {expanded === dataset!.dataset_id ? 'Hide fields' : 'Inspect fields'}</button><span>Repeatable reliability contract</span></footer></section>
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
  const documents = workspace?.documents ?? []
  return <main className="queue-page"><section className="page-heading"><div><h2>Invoices</h2><p>Uploaded invoice PDFs and their current status.</p></div></section><section className="queue-surface document-list">{loading ? <LoadingState label="Loading invoices" /> : documents.length ? documents.map((doc) => <article key={doc.id}><WorkIcon type="invoice_review" /><div><strong>{doc.filename}</strong><span>{shortId(doc.id)} - {formatDate(doc.created_at)}</span></div><Status value={doc.status} /></article>) : <EmptyState title="No invoices yet" body="Upload an invoice first." />}</section></main>
}

function HistoryPage({ workspace, loading, openItem }: { workspace?: Workspace; loading: boolean; openItem: (id: string) => void }) {
  const documentEvents = (workspace?.documents ?? []).map((document) => ({
    id: `document-${document.id}`,
    title: 'Invoice uploaded',
    body: document.filename,
    at: document.created_at,
    status: document.status,
    action: null as null | (() => void),
  }))
  const reviewEvents = (workspace?.work_items ?? []).map((item) => ({
    id: `item-${item.id}`,
    title: item.status === 'resolved' ? 'Review completed' : 'Review updated',
    body: item.title,
    at: item.updated_at,
    status: item.status,
    action: () => openItem(item.id),
  }))
  const events = [...documentEvents, ...reviewEvents].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime()).slice(0, 20)
  return (
    <main className="queue-page">
      <section className="page-heading">
        <div><h2>History</h2><p>A simple timeline of uploaded invoices and reviewer decisions.</p></div>
      </section>
      <section className="queue-surface history-list">
        {loading ? <LoadingState label="Loading history" /> : events.length ? events.map((event) => (
          <article key={event.id}>
            <span className="activity-dot source-system"><Check size={13} /></span>
            <div><strong>{event.title}</strong><p>{event.body}</p><small>{formatDate(event.at)}</small></div>
            <Status value={event.status} />
            {event.action ? <button className="outline-button" onClick={event.action}>Open</button> : null}
          </article>
        )) : <EmptyState title="No history yet" body="Upload an invoice, then review activity will appear here." />}
      </section>
    </main>
  )
}

function DocumentTab({ document, documentDetail, extraction, loading }: { document?: DocumentSummary; documentDetail?: ApiDocument; extraction: Extraction | null; loading: boolean }) {
  if (loading) return <LoadingState label="Loading invoice PDF" />
  if (!document) return <EmptyState title="No invoice PDF linked" body="Link an invoice PDF before reviewing this item." next="Do not approve invoice work until the PDF is linked or manually checked." />
  return <div className="document-review-layout"><AuthenticatedPdfPreview document={document} /><section className="panel document-evidence"><PanelTitle title="Invoice Data" action={<Status value={document.status} />} /><SchemaMeta document={documentDetail} extraction={extraction} /><div className="invoice-fields">{invoiceFields(extraction).map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong><small><i /> {value === '-' ? 'Missing' : 'Found'}</small></div>)}</div>{extraction?.confidence?.length ? <div className="evidence-list">{extraction.confidence.map((evidence) => <article key={evidence.field_name}><strong>{humanize(evidence.field_name)}</strong><EvidenceConfidence score={evidence.score} /><p>{evidence.source_text || 'No PDF snippet stored. Compare with the PDF before deciding.'}</p></article>)}</div> : <EmptyState title="No PDF snippets available" body="The app did not store snippets for these fields." next="Compare visible invoice values with the PDF before approving." />}{extraction?.validation?.length ? <div className="validation-list">{extraction.validation.map((issue, index) => <p key={index}><AlertTriangle size={14} /><span>{issue.message}</span></p>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No validation blockers.</div>}</section></div>
}

function SchemaMeta({ document, extraction, compact = false }: { document?: ApiDocument | DocumentSummary; extraction: Extraction | null; compact?: boolean }) {
  const documentType = extraction?.document_type ?? document?.document_type ?? 'invoice'
  return <div className={`schema-meta ${compact ? 'compact' : ''}`}><span><FileText size={12} /> {humanize(documentType)}</span></div>
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
  return <div className="tab-content"><div className="draft-history-heading"><div><h3>Draft Version History</h3><p>Every regeneration creates a separate reviewable record.</p></div><span>{item.drafts.length} versions</span></div>{item.drafts.length ? [...item.drafts].reverse().map((draft, index) => <section className="panel draft-card" key={draft.id}><PanelTitle title={`${humanize(draft.draft_type)} Â· Version ${item.drafts.length - index}`} action={<Status value={draft.status} />} />{editing === draft.id ? <textarea className="draft-editor" value={content} onChange={(event) => setContent(event.target.value)} /> : <pre>{draft.preview_content}</pre>}<small>Updated {formatDate(draft.updated_at)}</small><div className="panel-actions">{editing === draft.id ? <><button className="outline-button" onClick={() => setEditing('')}>Cancel</button><button className="primary-button" disabled={!content.trim() || edit.isPending} onClick={() => edit.mutate({ id: draft.id, value: content })}><Check size={14} /> Save Draft</button></> : <><button className="outline-button" disabled={regenerate.isPending} onClick={() => regenerate.mutate(draft.id)}><RefreshCw size={14} /> Regenerate</button><button className="outline-button" disabled={draft.status !== 'drafted'} onClick={() => { setEditing(draft.id); setContent(draft.preview_content) }}><Pencil size={14} /> Edit</button></>}</div></section>) : <EmptyState title="No drafts" body="Drafts produced by the plan will appear here." />}</div>
}

function ApprovalTab({ item, document, extraction }: { item: WorkItemDetail; document?: DocumentSummary; extraction: Extraction | null }) {
  const queryClient = useQueryClient()
  const pending = item.approvals.find((approval) => approval.status === 'pending')
  const [notes, setNotes] = useState('')
  const decision = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api(`/backoffice/approvals/${pending?.id}/${action}`, { method: 'POST', body: JSON.stringify({ notes: notes.trim() || `${humanize(action)} after guided review.` }) }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['workspace'] }); queryClient.invalidateQueries({ queryKey: ['work-item', item.id] }) },
  })
  const correction = useMutation({
    mutationFn: () => api(`/documents/${document?.id}/request-correction`, { method: 'POST', body: JSON.stringify({ reason: notes.trim() || 'Please correct the invoice information before approval.' }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace'] })
      queryClient.invalidateQueries({ queryKey: ['work-item', item.id] })
      queryClient.invalidateQueries({ queryKey: ['document-workflow', document?.id] })
    },
  })
  const latestDecision = [...item.approvals].reverse().find((approval) => approval.status !== 'pending')
  const executed = [...item.activity].reverse().find((event) => ['action_executed','action_failed'].includes(event.event_type))
  const signals = exceptionSignals(item, extraction)
  const evidence = extraction?.confidence ?? []
  const validation = extraction?.validation ?? []
  const latestPolicy = item.policy_decisions.at(-1)
  const pendingStep = item.current_plan?.steps.find((candidate) => candidate.id === pending?.action_step_id) ?? item.current_plan?.steps.find((step) => step.requires_approval) ?? item.current_plan?.steps[0]
  const approvalReason = latestPolicy?.reason ?? item.current_plan?.escalation_reason ?? pendingStep?.why_this ?? 'This action can affect document records and needs a reviewer decision before execution.'

  return (
    <div className="decision-page">
      <section className="panel decision-hero">
        <PanelTitle title="Decision Needed" action={<Status value={item.status} />} />
        <p>{approvalReason}</p>
        <div className="exception-signal-grid">{signals.map((signal) => <article className={`exception-signal exception-${signal.tone}`} key={signal.label}><AlertTriangle size={15} /><div><strong>{signal.label}</strong><p>{signal.detail}</p></div></article>)}</div>
      </section>

      <section className="panel decision-checklist">
        <PanelTitle title="Check Before You Decide" action={<span className="version">{evidence.length} fields</span>} />
        <div className="evidence-snapshot">
          <DetailField label="Invoice" value={document?.filename ?? 'No linked PDF'} />
          <DetailField label="Issues found" value={validation.length} />
          <DetailField label="Fields checked" value={evidence.length} />
          <DetailField label="Recommended next step" value={pendingStep ? businessActionLabel(pendingStep.action_type) : 'Review invoice'} />
        </div>
        {validation.length ? <div className="validation-issues compact">{validation.slice(0, 3).map((issue, index) => <article key={index}><AlertTriangle size={14} /><div><strong>{humanize(issue.field_name ?? issue.field ?? 'Invoice data')}</strong><p>{issue.message ?? 'This needs review.'}</p></div></article>)}</div> : <div className="validation-ok"><CheckCircle2 size={15} /> No blockers found.</div>}
        <EvidenceExcerpts evidence={evidence} />
      </section>

      <section className="panel decision-action-panel">
        <PanelTitle title="Make Decision" />
        {pending ? <>
          <label className="decision-notes"><span>Decision note</span><textarea value={notes} placeholder="What did you check?" onChange={(event) => setNotes(event.target.value)} /></label>
          <p className="decision-guidance"><FileClock size={14} /> Approve only when the invoice details match the PDF. Ask for correction when vendor, amount, tax, or invoice number is missing or wrong.</p>
          <div className="decision-choice-grid">
            <button className="approve-action" disabled={decision.isPending || correction.isPending} onClick={() => decision.mutate('approve')}><CheckCircle2 size={15} /> Approve invoice</button>
            <button className="reject-action" disabled={decision.isPending || correction.isPending} onClick={() => decision.mutate('reject')}><X size={15} /> Reject</button>
            <button className="outline-button" disabled={!document || decision.isPending || correction.isPending} onClick={() => correction.mutate()}><Pencil size={15} /> Ask for correction</button>
          </div>
          {decision.error || correction.error ? <p className="form-error">{((decision.error || correction.error) as Error).message}</p> : null}
        </> : latestDecision ? <div className="decision-result"><Status value={latestDecision.status} /><p>{latestDecision.reviewer_notes || 'Decision recorded without notes.'}</p><small>{latestDecision.reviewed_by} - {latestDecision.reviewed_at ? formatDate(latestDecision.reviewed_at) : ''}</small></div> : <p>No decision is required right now.</p>}
      </section>

      <section className="panel decision-result-panel">
        <PanelTitle title="Result" />
        {executed ? <div className={`notice ${executed.event_type === 'action_executed' ? 'success' : 'danger'}`}><Activity size={17} /><div><strong>{activityLabel(executed.event_type)}</strong><p>{executed.summary}</p><small>{executed.actor} - {formatDate(executed.created_at)}</small></div></div> : <div className="notice"><FileClock size={17} /><div><strong>Not finished yet</strong><p>The result will appear here after the decision is completed.</p></div></div>}
      </section>
    </div>
  )

}

function EvidenceExcerpts({ evidence = [] }: { evidence?: Extraction['confidence'] }) {
  const excerpts = evidence.filter((entry) => entry.source_text).slice(0, 3)
  if (!excerpts.length) return <div className="missing-evidence"><AlertTriangle size={16} /><div><strong>No PDF snippets available</strong><p>Compare the invoice details with the PDF before deciding.</p></div></div>
  return (
    <div className="approval-evidence-excerpts">
      {excerpts.map((entry) => <article key={entry.field_name}><strong>{humanize(entry.field_name)}</strong><EvidenceConfidence score={entry.score} /><p>{entry.source_text}</p></article>)}
    </div>
  )
}

function AgentOpsTab({ item }: { item: WorkItemDetail }) {
  const linked = item.activity.filter((event) => event.agent_run_id)
  return <div className="tab-content"><TraceCard item={item} />{linked.length ? <section className="panel"><PanelTitle title="Linked Trace Activity" /><div className="activity-list">{linked.map((event) => <article key={event.id}><span className="activity-dot source-agentops"><Activity size={13} /></span><div><strong>{humanize(event.event_type)}</strong><p>{event.summary}</p><small>Run {shortId(event.agent_run_id!)} Â· {formatDate(event.created_at)}</small></div><button className="outline-button" onClick={() => window.open(`/ui/agentops?run_id=${event.agent_run_id}`, '_blank')}>Open trace</button></article>)}</div></section> : null}</div>
}

const hiddenDetailViews = [PlanTab, RecordTab, GovernanceTab, AgentOpsTab] as const
void hiddenDetailViews

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
  if (loading) return <LoadingState label="Loading history" />
  if (error) return <ErrorState message={error.message} retry={() => queryClient.invalidateQueries({ queryKey: ['document-workflow', documentId] })} />
  if (!workflow) return <EmptyState title="No history yet" body="History appears after the invoice is uploaded, checked, or reviewed." />
  return <div className="activity-tab">
    <section className="workflow-orientation">
      <DetailField label="Status" value={invoiceStageCopy(workflow.current_stage)} />
      <DetailField label="Owner" value={workflow.current_owner} />
      <DetailField label="Waiting for" value={workflow.waiting_for ? plainNextAction(workflow.waiting_for) : 'Nothing right now'} />
      <DetailField label="Next" value={plainNextAction(workflow.next_action)} />
      {workflow.attention_reason ? <div className="notice warning"><AlertTriangle size={16} /><div><strong>Attention required</strong><p>{workflow.attention_reason}</p></div></div> : null}
    </section>
    <section className="panel workflow-activity">
      <PanelTitle title="History" action={<span className="version">{workflow.activity.length} updates</span>} />
      <div className="activity-list">{workflow.activity.map((event) => <article key={event.id}><span className={`activity-dot source-${event.source}`}><Check size={13} /></span><div><strong>{activityLabel(event.event_type)}</strong><p>{event.summary}</p><small>{event.actor} - {formatDate(event.created_at)}</small></div></article>)}</div>
      {!workflow.activity.length ? <EmptyState title="No history yet" body="No upload, check, approval, or correction updates have been saved yet." next="Upload, check, or decide on an invoice to create history." /> : null}
    </section>
    <section className="panel recovery-panel">
      <PanelTitle title="Fix invoice" />
      <p>Use these only when the invoice needs another read, a correction request, or reviewer help. Every action is saved in history.</p>
      {workflow.work_item ? <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason or correction note" /> : null}
      <div className="panel-actions">
        {workflow.current_stage === 'failed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('retry')}><RefreshCw size={14} /> Read again</button> : null}
        {workflow.work_item && workflow.current_stage !== 'completed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('request-correction')}><Pencil size={14} /> Ask for correction</button> : null}
        {workflow.work_item && workflow.current_stage !== 'completed' ? <button className="outline-button" disabled={command.isPending} onClick={() => command.mutate('escalate')}><UserRound size={14} /> Send to reviewer</button> : null}
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
  return <span className={`badge status-${value}`}>{statusLabel(value)}</span>
}
function Priority({ value }: { value: string }) {
  return <span className={`priority priority-${value}`}><i />{humanize(value)}</span>
}
function TypeBadge({ value }: { value: string | null }) {
  return <span className={`type-badge type-${value ?? 'unknown'}`}>{humanize(value ?? 'unclassified')}</span>
}
function EvidenceConfidence({ score }: { score: number | null }) {
  const level = score == null ? 'unknown' : score >= .85 ? 'high' : score >= .65 ? 'medium' : 'low'
  const label = matchCopy(score)
  return <span className={`confidence confidence-${level}`}>{label}</span>
}
function matchCopy(score: number | null) {
  if (score == null) return 'Not checked'
  if (score >= .85) return 'Strong match'
  if (score >= .65) return 'Needs check'
  return 'Review carefully'
}
function WorkIcon({ type }: { type: string | null }) {
  const Icon = type?.includes('invoice') ? FileText : type?.includes('vendor') ? Database : type?.includes('accounting') ? FileCheck2 : Zap
  return <span className={`work-icon ${type?.includes('invoice') ? 'red' : type?.includes('vendor') ? 'green' : 'purple'}`}><Icon size={17} /></span>
}
function EmptyState({ title, body, next }: { title: string; body: string; next?: string }) {
  return <div className="empty-state"><FileText size={24} /><strong>{title}</strong><span>{body}</span>{next ? <small>{next}</small> : null}</div>
}
function LoadingState({ label = 'Loading workspace' }: { label?: string } = {}) {
  return <div className="loading-state"><Loader2 className="spin" size={20} /><span>{label}</span></div>
}
function ErrorState({ message, retry }: { message: string; retry: () => void }) {
  const secureSession = /session|auth|verify|credential|401|403/i.test(message)
  return <main className="error-state"><AlertTriangle size={26} /><h2>{secureSession ? 'Unable to verify secure session' : 'Unable to load workspace'}</h2><p>{secureSession ? 'Refresh the session, then try again. If it keeps failing, sign in again before continuing invoice work.' : 'The app could not reach the invoice workspace. Retry once, then check that the backend is running.'}</p><small>Technical detail is available in the browser console or server logs.</small><button className="primary-button" onClick={retry}><RefreshCw size={15} /> Retry</button></main>
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
function invoiceAmount(document: InvoiceListItem) {
  return document.total ? `${document.currency || ''} ${document.total}`.trim() : 'Amount unavailable'
}
function invoiceStageCopy(value: string) {
  const labels: Record<string, string> = {
    uploaded: 'Uploaded',
    queued: 'Waiting to be read',
    extracting: 'Reading invoice',
    processing: 'Reading invoice',
    needs_attention: 'Needs review',
    needs_review: 'Needs review',
    planning: 'Preparing review',
    awaiting_human: 'Waiting approval',
    waiting_approval: 'Waiting approval',
    approved: 'Approved',
    rejected: 'Rejected',
    completed: 'Completed',
    resolved: 'Completed',
    failed: 'Needs correction',
    blocked: 'Needs correction',
  }
  return labels[value] ?? statusLabel(value)
}
function plainNextAction(value: string) {
  const normalized = value.toLowerCase()
  if (normalized.includes('approve') || normalized.includes('approval')) return 'Reviewer decision'
  if (normalized.includes('review')) return 'Review invoice'
  if (normalized.includes('correct')) return 'Ask for correction'
  if (normalized.includes('export')) return 'Prepare export'
  return value
}
function activityLabel(value: string) {
  const labels: Record<string, string> = {
    uploaded: 'Invoice uploaded',
    document_uploaded: 'Invoice uploaded',
    processing_started: 'Reading started',
    processing_succeeded: 'Invoice read',
    processing_failed: 'Reading failed',
    work_created: 'Review created',
    plan_created: 'Next step prepared',
    approval_requested: 'Approval requested',
    approval_approved: 'Approved',
    approval_rejected: 'Rejected',
    correction_requested: 'Correction requested',
    action_executed: 'Completed',
    action_failed: 'Could not complete',
    escalated: 'Sent to reviewer',
  }
  return labels[value] ?? humanize(value)
}
function businessActionLabel(value: string) {
  const labels: Record<string, string> = {
    invoice_review: 'Check invoice',
    invoice_export: 'Prepare approved invoice export',
    accounting_note: 'Prepare accounting note',
    vendor_follow_up: 'Ask vendor for information',
    exception_handling: 'Resolve invoice issue',
    insufficient_evidence: 'Ask for correction',
  }
  return labels[value] ?? humanize(value)
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
  if (status === 'awaiting_human') return 'Make Decision'
  if (status === 'ready_to_execute') return 'Continue'
  if (status === 'blocked') return 'View Reason'
  if (status === 'resolved') return 'View Result'
  return 'Review Invoice'
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
  return { new: 'Upload Invoice', submissions: 'My Invoices', invoices: 'Invoices', guide: 'Guide' }[view]
}
function outcomeCopy(workType: string) {
  const copy: Record<string, string> = {
    invoice_review: 'Create a review task to check extracted fields and validation evidence.',
    accounting_note: 'Create a reviewable accounting note draft. Nothing is posted externally.',
    invoice_export: 'Check approved invoice evidence and prepare an export that requires human approval before execution.',
    vendor_follow_up: 'Create a reviewable vendor message draft. Nothing is sent automatically.',
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
  if (item.status === 'awaiting_human') return 'Waiting for reviewer decision'
  if (item.status === 'blocked') return 'Blocked until a reviewer checks it'
  if (item.status === 'failed') return 'Processing failed'
  return 'Needs reviewer check'
}
function decisionRequired(item: WorkItemSummary) {
  if (item.status === 'awaiting_human') return 'Approve, reject, ask for correction, or escalate.'
  if (item.status === 'blocked') return 'Check the reason and choose the next safe step.'
  if (item.status === 'failed') return 'Check the failure and retry if needed.'
  return 'Check the invoice and choose the next action.'
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
  if (lowConfidence.length) signals.push({ label: 'Needs careful check', detail: `${lowConfidence.length} invoice field${lowConfidence.length === 1 ? '' : 's'} may not match the PDF.`, tone: 'warning' })
  if (!extraction?.confidence?.length && item.linked_document_ids.length) signals.push({ label: 'PDF snippets unavailable', detail: 'The app did not store snippets for this invoice. Compare the values with the PDF before deciding.', tone: 'warning' })
  if (item.status === 'awaiting_human') signals.push({ label: 'Decision needed', detail: 'A reviewer must approve or reject this invoice before it continues.', tone: 'neutral' })
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
function statusLabel(value: string) {
  const labels: Record<string, string> = {
    queued: 'Reading invoice',
    processing: 'Reading invoice',
    extracted: 'Needs review',
    needs_review: 'Needs review',
    awaiting_human: 'Waiting approval',
    ready_to_execute: 'Ready to continue',
    executing: 'In progress',
    classified: 'In progress',
    planning: 'In progress',
    approved: 'Approved',
    rejected: 'Rejected',
    resolved: 'Completed',
    completed: 'Completed',
    blocked: 'Needs correction',
    failed: 'Needs correction',
    draft: 'Draft',
    drafted: 'Draft',
    pending: 'Waiting approval',
  }
  return labels[value] ?? humanize(value)
}
function shortId(id: string) {
  return id.slice(0, 8)
}

export default App
