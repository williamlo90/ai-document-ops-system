import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  CloudUpload,
  Database,
  FileCheck2,
  FileSearch,
  FolderLock,
  History,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  ServerCog,
  X,
} from 'lucide-react'
import { api } from '../api/client'
import type {
  SystemAudit,
  SystemDashboard,
  SystemFlowStage,
  SystemIntegration,
  SystemJob,
  SystemService,
  SystemStatus,
} from '../features/system/types'
import { formatDate, humanize } from '../features/invoices/format'
import { Button, EmptyState, ErrorState, Panel, SkeletonRows, StatusBadge } from '../shared/ui'

const tabs = ['status', 'processing', 'integrations', 'audit'] as const
type SystemTab = (typeof tabs)[number]

export function SystemPage() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const tab = tabs.includes(params.get('tab') as SystemTab) ? params.get('tab') as SystemTab : 'status'
  const filter = params.get('filter')
  const stage = params.get('stage')
  const [service, setService] = useState<SystemService | null>(null)
  const [job, setJob] = useState<SystemJob | null>(null)
  const [audit, setAudit] = useState<SystemAudit | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const attentionRef = useRef<HTMLElement>(null)

  const dashboard = useQuery({
    queryKey: ['system-dashboard'],
    queryFn: () => api<SystemDashboard>('/system/dashboard'),
    refetchInterval: 15_000,
  })
  const retry = useMutation({
    mutationFn: (id: string) => api(`/operations/jobs/${id}/retry`, { method: 'POST' }),
    onSuccess: () => {
      setJob(null)
      setToast('Retry accepted. The invoice is waiting to be processed again.')
      void queryClient.invalidateQueries({ queryKey: ['system-dashboard'] })
    },
  })

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const setTab = (value: SystemTab, nextFilter?: string | null, nextStage?: string | null) => {
    updateParams(params, setParams, { tab: value === 'status' ? null : value, filter: nextFilter ?? null, stage: nextStage ?? null })
  }
  const refresh = async () => {
    const result = await dashboard.refetch()
    if (!result.error) setToast('System status refreshed.')
  }
  const showAttention = () => {
    setTab('status')
    window.setTimeout(() => attentionRef.current?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'center' }), 30)
  }
  const openAlert = (targetId: string, kind: string) => {
    if (kind === 'service') setService(dashboard.data?.services.find((item) => item.id === targetId) ?? null)
    else setJob(dashboard.data?.recent_jobs.find((item) => item.id === targetId) ?? null)
  }

  return <div className="ops-page system-page">
    <header className="system-header">
      <div><h1>System</h1><p>Monitor invoice processing and connected services.</p></div>
      <div><Button disabled={dashboard.isFetching} onClick={() => void refresh()}>{dashboard.isFetching ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />} {dashboard.isFetching ? 'Refreshing...' : 'Refresh status'}</Button><span>{dashboard.data ? `Observed ${formatDate(dashboard.data.observed_at, true)}` : 'Waiting for status'}</span></div>
    </header>

    {dashboard.isLoading ? <SystemSkeleton /> : dashboard.error ? <ErrorState message={(dashboard.error as Error).message} retry={() => void dashboard.refetch()} /> : dashboard.data ? <>
      <OverallBanner data={dashboard.data} open={() => setService(dashboard.data!.services.find((item) => item.status !== 'operational') ?? dashboard.data!.services[0])} />
      <SystemKpis data={dashboard.data} setTab={setTab} showAttention={showAttention} />
      <div className="system-page-layout">
        <div className="system-primary">
          <SystemTabs active={tab} select={setTab} />
          {tab === 'status' ? <StatusView data={dashboard.data} openService={setService} openJob={setJob} /> : null}
          {tab === 'processing' ? <ProcessingView data={dashboard.data} filter={filter} stage={stage} clear={() => setTab('processing')} openJob={setJob} retry={(item) => retry.mutate(item.id)} pending={retry.isPending} /> : null}
          {tab === 'integrations' ? <IntegrationsView data={dashboard.data.integrations} open={(item) => setService(dashboard.data!.services.find((serviceItem) => serviceItem.id === item.id) ?? null)} /> : null}
          {tab === 'audit' ? <AuditView data={dashboard.data.audit} open={setAudit} /> : null}
        </div>
        <aside className="system-rail">
          <AttentionPanel ref={attentionRef} data={dashboard.data} open={openAlert} />
          <FlowPanel data={dashboard.data} open={(item) => setTab('processing', null, item.id)} />
          <ConnectedServices data={dashboard.data.integrations} open={(item) => setService(dashboard.data!.services.find((serviceItem) => serviceItem.id === item.id) ?? null)} />
          <Panel className="system-maintenance"><header><h2>Maintenance &amp; status</h2><History size={17} /></header><strong>{dashboard.data.maintenance.title}</strong><p>{dashboard.data.maintenance.detail}</p></Panel>
        </aside>
      </div>
    </> : null}

    {service ? <ServiceDrawer service={service} close={() => setService(null)} /> : null}
    {job ? <JobDrawer job={job} pending={retry.isPending} error={retry.error as Error | null} close={() => setJob(null)} retry={() => retry.mutate(job.id)} /> : null}
    {audit ? <AuditDrawer audit={audit} close={() => setAudit(null)} /> : null}
    {toast ? <div className="ops-toast" role="status"><CheckCircle2 size={17} />{toast}<button aria-label="Dismiss message" onClick={() => setToast(null)}><X size={14} /></button></div> : null}
  </div>
}

function OverallBanner({ data, open }: { data: SystemDashboard; open: () => void }) {
  const icon = data.overall.status === 'operational' ? <CheckCircle2 /> : data.overall.status === 'unknown' ? <CircleHelp /> : <AlertTriangle />
  return <Panel className={`system-overall is-${data.overall.status}`}><span>{icon}</span><div><strong>{data.overall.title}</strong><p>{data.overall.detail}</p></div><Button onClick={open}>View status details</Button></Panel>
}

function SystemKpis({ data, setTab, showAttention }: { data: SystemDashboard; setTab: (tab: SystemTab, filter?: string | null) => void; showAttention: () => void }) {
  const items = [
    { label: 'Processing now', value: data.kpis.processing_now, icon: <RefreshCw />, tone: 'info', action: () => setTab('processing', 'active') },
    { label: 'Waiting', value: data.kpis.waiting, icon: <Clock3 />, tone: 'warning', action: () => setTab('processing', 'waiting') },
    { label: 'Completed today', value: data.kpis.completed_today, icon: <CheckCircle2 />, tone: 'success', action: () => setTab('processing', 'completed') },
    { label: 'Needs attention', value: data.kpis.needs_attention, icon: <AlertCircle />, tone: 'danger', action: showAttention },
  ]
  return <div className="system-kpis" aria-label="System workload summary">{items.map((item) => <button key={item.label} onClick={item.action}><span className={`ops-kpi__icon ops-tone-${item.tone}`}>{item.icon}</span><span><strong>{item.value}</strong><small>{item.label}</small></span></button>)}</div>
}

function SystemTabs({ active, select }: { active: SystemTab; select: (value: SystemTab) => void }) {
  return <div className="system-tabs" role="tablist" aria-label="System views">{tabs.map((item) => <button key={item} role="tab" aria-selected={active === item} className={active === item ? 'is-active' : ''} onClick={() => select(item)}>{humanize(item)}</button>)}</div>
}

function StatusView({ data, openService, openJob }: { data: SystemDashboard; openService: (item: SystemService) => void; openJob: (item: SystemJob) => void }) {
  return <div className="system-status-view">
    <Panel className="system-service-panel"><header><div><h2>Core service status</h2><p>Current checks and observed workspace activity.</p></div></header><div className="ops-table-wrap"><table className="ops-table system-service-table"><thead><tr><th>Service</th><th>Status</th><th>Uptime</th><th>Last observation</th><th>Recent activity</th><th>Action</th></tr></thead><tbody>{data.services.map((service) => <tr key={service.id} className={service.status === 'degraded' || service.status === 'unavailable' ? 'is-attention' : ''}><td><ServiceIcon id={service.id} />{service.name}</td><td><ServiceBadge status={service.status} /></td><td title="Historical health snapshots are not persisted yet.">{service.uptime_label}</td><td>{service.observed_at ? formatDate(service.observed_at, true) : 'Not observed'}</td><td>{service.activity}</td><td><button className="ops-link" onClick={() => openService(service)}>{service.status === 'degraded' || service.status === 'unavailable' ? 'Investigate' : 'View'} <ChevronRight size={13} /></button></td></tr>)}</tbody></table></div><footer>Uptime remains unavailable until enough persisted health history exists.</footer></Panel>
    <RecentJobs jobs={data.recent_jobs.slice(0, 5)} open={openJob} />
  </div>
}

function ProcessingView({ data, filter, stage, clear, openJob, retry, pending }: { data: SystemDashboard; filter: string | null; stage: string | null; clear: () => void; openJob: (item: SystemJob) => void; retry: (item: SystemJob) => void; pending: boolean }) {
  const jobs = useMemo(() => data.recent_jobs.filter((job) => {
    const filterMatch = !filter || (filter === 'active' && job.status === 'running') || (filter === 'waiting' && ['queued', 'retrying'].includes(job.status)) || (filter === 'completed' && job.status === 'succeeded') || (filter === 'attention' && ['failed', 'dead_letter'].includes(job.status))
    const stageMatch = !stage || stageMatches(stage, job)
    return filterMatch && stageMatch
  }), [data.recent_jobs, filter, stage])
  return <Panel className="system-processing-panel"><header><div><h2>Processing activity</h2><p>Sanitized job state for this workspace.</p></div>{filter || stage ? <button className="system-filter-chip" onClick={clear}>{filter ? humanize(filter) : humanize(stage!)} <X size={13} /></button> : null}</header>{jobs.length ? <JobTable jobs={jobs} open={openJob} retry={retry} pending={pending} /> : <EmptyState title="No processing activity matches this view" body="Clear the current filter or wait for new invoice processing." action={<Button onClick={clear}>Clear filter</Button>} />}</Panel>
}

function IntegrationsView({ data, open }: { data: SystemIntegration[]; open: (item: SystemIntegration) => void }) {
  return <Panel className="system-integrations-panel"><header><div><h2>Connected services</h2><p>Configuration and observed state without credentials or raw provider responses.</p></div></header><div className="system-integration-list">{data.map((item) => <button key={item.id} onClick={() => open(item)}><ServiceIcon id={item.id} /><span><strong>{item.name}</strong><small>{item.provider || 'Built-in service'}</small></span><ServiceBadge status={item.status} /><ChevronRight size={16} /></button>)}</div></Panel>
}

function AuditView({ data, open }: { data: SystemAudit[]; open: (item: SystemAudit) => void }) {
  return <Panel className="system-audit-panel"><header><div><h2>Audit activity</h2><p>Immutable business events; raw payloads and secrets are not shown.</p></div><a className="ops-button ops-button--secondary" href="/operations/audit.csv">Download CSV</a></header>{data.length ? <div className="ops-table-wrap"><table className="ops-table"><thead><tr><th>Timestamp</th><th>Actor</th><th>Action</th><th>Target</th><th>Result</th><th /></tr></thead><tbody>{data.map((item) => <tr key={item.id}><td>{formatDate(item.timestamp, true)}</td><td>{item.actor}</td><td>{item.action}</td><td>{item.target}</td><td><StatusBadge tone="neutral">{humanize(item.result)}</StatusBadge></td><td><button className="ops-link" onClick={() => open(item)}>View</button></td></tr>)}</tbody></table></div> : <EmptyState title="No audit activity yet" body="Upload and review events will appear here." />}</Panel>
}

const AttentionPanel = ({ data, open, ref }: { data: SystemDashboard; open: (target: string, kind: string) => void; ref: React.Ref<HTMLElement> }) => <Panel className="system-attention" ariaLabel="Needs attention"><section ref={ref}><header><h2>Needs attention</h2><span>{data.alerts.length}</span></header>{data.alerts.length ? data.alerts.slice(0, 4).map((alert) => <button key={alert.id} onClick={() => open(alert.target_id, alert.kind)}><AlertTriangle size={17} /><span><strong>{alert.title}</strong><small>{alert.detail}</small></span><ChevronRight size={15} /></button>) : <div className="system-healthy"><CheckCircle2 size={21} /><span><strong>No unresolved alerts</strong><small>Current observed checks do not require action.</small></span></div>}</section></Panel>

function FlowPanel({ data, open }: { data: SystemDashboard; open: (item: SystemFlowStage) => void }) {
  return <Panel className="system-flow" ariaLabel="Processing flow"><header><div><h2>Processing flow</h2><p>{data.flow.window_label}</p></div></header><div>{data.flow.stages.map((stage, index) => <button key={stage.id} onClick={() => open(stage)}><span className="system-flow-icon">{index === 0 ? <CloudUpload /> : index < 4 ? <FileSearch /> : <FileCheck2 />}</span><span>{stage.label}</span><strong>{stage.count}</strong><b>{stage.conversion_percent == null ? '-' : `${stage.conversion_percent}%`}</b></button>)}</div><footer>{data.flow.denominator}</footer></Panel>
}

function ConnectedServices({ data, open }: { data: SystemIntegration[]; open: (item: SystemIntegration) => void }) {
  return <Panel className="system-connected"><header><h2>Connected services</h2></header>{data.map((item) => <button key={item.id} onClick={() => open(item)}><ServiceIcon id={item.id} /><span>{item.name}</span><ServiceBadge status={item.status} /></button>)}</Panel>
}

function RecentJobs({ jobs, open }: { jobs: SystemJob[]; open: (item: SystemJob) => void }) {
  return <Panel className="system-recent"><header><div><h2>Recent processing</h2><p>Latest invoice reading jobs.</p></div><Link className="ops-link" to="/admin/operations?tab=processing">View all processing <ChevronRight size={13} /></Link></header>{jobs.length ? <JobTable jobs={jobs} open={open} /> : <EmptyState title="No recent processing activity" body="New invoice jobs will appear here once processing begins." />}</Panel>
}

function JobTable({ jobs, open, retry, pending }: { jobs: SystemJob[]; open: (item: SystemJob) => void; retry?: (item: SystemJob) => void; pending?: boolean }) {
  return <div className="ops-table-wrap"><table className="ops-table system-job-table"><thead><tr><th>Invoice</th><th>Stage</th><th>Status</th><th>Started</th><th>Duration</th><th>Attempts</th><th>Action</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><Link className="ops-link" to={`/review/${job.document_id}`}>{job.invoice}</Link><small>{job.filename}</small></td><td>{job.stage}</td><td><JobBadge status={job.status} /></td><td>{formatDate(job.started_at, true)}</td><td>{formatDuration(job.duration_ms)}</td><td>{job.attempt_count}</td><td>{job.retryable && retry ? <button className="ops-link" disabled={pending} onClick={() => retry(job)}>Retry <RotateCcw size={13} /></button> : <button className="ops-link" onClick={() => open(job)}>View <ChevronRight size={13} /></button>}</td></tr>)}</tbody></table></div>
}

function ServiceDrawer({ service, close }: { service: SystemService; close: () => void }) {
  return <Drawer eyebrow="Service status" title={service.name} close={close}><div className="system-drawer-verdict"><ServiceBadge status={service.status} /><strong>{service.provider || 'Built-in capability'}</strong><span>{service.observed_at ? `Observed ${formatDate(service.observed_at, true)}` : 'No observed provider run'}</span></div><dl><div><dt>Uptime</dt><dd>{service.uptime_label}</dd></div><div><dt>Recent activity</dt><dd>{service.activity}</dd></div></dl><section><h3>Evidence</h3><p>{service.evidence}</p></section>{service.affected_capability ? <section className="system-impact"><h3>Affected</h3><p>{service.affected_capability}</p></section> : null}{service.unaffected_capability ? <section><h3>Still available</h3><p>{service.unaffected_capability}</p></section> : null}</Drawer>
}

function JobDrawer({ job, pending, error, close, retry }: { job: SystemJob; pending: boolean; error: Error | null; close: () => void; retry: () => void }) {
  return <Drawer eyebrow="Processing trace" title={job.invoice} close={close}><div className="system-drawer-verdict"><JobBadge status={job.status} /><strong>{job.stage}</strong><span>{job.filename}</span></div><dl><div><dt>Started</dt><dd>{formatDate(job.started_at, true)}</dd></div><div><dt>Finished</dt><dd>{formatDate(job.finished_at, true)}</dd></div><div><dt>Duration</dt><dd>{formatDuration(job.duration_ms)}</dd></div><div><dt>Attempts</dt><dd>{job.attempt_count}</dd></div></dl>{job.failure_summary ? <section className="system-impact"><h3>What happened</h3><p>{job.failure_summary}</p></section> : null}{error ? <p className="system-drawer-error"><AlertCircle size={16} />{error.message}</p> : null}<footer><Link className="ops-button ops-button--secondary" to={`/review/${job.document_id}`}>Open invoice</Link>{job.retryable ? <Button variant="primary" disabled={pending} onClick={retry}>{pending ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />} {pending ? 'Accepting retry...' : 'Retry processing'}</Button> : null}</footer></Drawer>
}

function AuditDrawer({ audit, close }: { audit: SystemAudit; close: () => void }) {
  return <Drawer eyebrow="Audit event" title={audit.action} close={close}><div className="system-drawer-verdict"><StatusBadge tone="neutral">{humanize(audit.result)}</StatusBadge><strong>{audit.target}</strong><span>{formatDate(audit.timestamp, true)}</span></div><dl><div><dt>Actor</dt><dd>{audit.actor}</dd></div><div><dt>Event ID</dt><dd>{audit.id}</dd></div></dl><section><h3>Record boundary</h3><p>This view exposes the event outcome only. Raw payloads, prompts, credentials, and provider responses remain hidden.</p></section></Drawer>
}

function Drawer({ eyebrow, title, close, children }: { eyebrow: string; title: string; close: () => void; children: ReactNode }) {
  return <div className="ops-modal-backdrop system-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close() }}><aside className="system-drawer" role="dialog" aria-modal="true" aria-labelledby="system-drawer-title"><header><div><span>{eyebrow}</span><h2 id="system-drawer-title">{title}</h2></div><button className="ops-icon-button" aria-label="Close details" onClick={close}><X size={19} /></button></header>{children}</aside></div>
}

function ServiceBadge({ status }: { status: SystemStatus }) {
  const tone = status === 'operational' ? 'success' : status === 'degraded' ? 'warning' : status === 'unavailable' ? 'danger' : 'neutral'
  return <StatusBadge tone={tone}>{humanize(status)}</StatusBadge>
}

function JobBadge({ status }: { status: SystemJob['status'] }) {
  const tone = status === 'succeeded' ? 'success' : status === 'running' ? 'info' : ['queued', 'retrying'].includes(status) ? 'warning' : ['failed', 'dead_letter'].includes(status) ? 'danger' : 'neutral'
  return <StatusBadge tone={tone}>{status === 'succeeded' ? 'Completed' : humanize(status)}</StatusBadge>
}

function ServiceIcon({ id }: { id: string }) {
  const props = { size: 16, 'aria-hidden': true } as const
  if (id === 'uploads') return <CloudUpload {...props} />
  if (id === 'reader') return <FileSearch {...props} />
  if (id === 'extractor') return <Database {...props} />
  if (id === 'storage') return <FolderLock {...props} />
  if (id === 'accounting_export') return <FileCheck2 {...props} />
  return <ServerCog {...props} />
}

function SystemSkeleton() {
  return <div className="system-skeleton"><Panel><SkeletonRows count={2} /></Panel><div className="system-kpis">{Array.from({ length: 4 }, (_, index) => <Panel key={index}><SkeletonRows count={2} /></Panel>)}</div><div className="system-page-layout"><Panel><SkeletonRows count={9} /></Panel><Panel><SkeletonRows count={8} /></Panel></div></div>
}

function stageMatches(stage: string, job: SystemJob) {
  if (stage === 'upload') return ['queued'].includes(job.status)
  if (stage === 'read') return ['running', 'succeeded', 'failed', 'dead_letter'].includes(job.status)
  if (['extract', 'checks'].includes(stage)) return job.status === 'succeeded'
  return false
}

function formatDuration(value: number | null) {
  if (value == null) return '-'
  if (value < 1000) return `${value}ms`
  const seconds = value / 1000
  return seconds < 60 ? `${seconds.toFixed(seconds < 10 ? 1 : 0)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function reducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function updateParams(current: URLSearchParams, setter: ReturnType<typeof useSearchParams>[1], values: Record<string, string | null>) {
  const next = new URLSearchParams(current)
  Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
  setter(next)
}
