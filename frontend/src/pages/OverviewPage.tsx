import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleCheckBig,
  Clock3,
  FileCheck2,
  FileSearch,
  ListChecks,
  Sparkles,
  TriangleAlert,
  Upload,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import type {
  OverviewAlert,
  OverviewDashboard,
  OverviewKpi,
  OverviewQueueItem,
} from '../features/overview/types'
import { formatDate, formatMoney } from '../features/invoices/format'
import { EmptyState, ErrorState, Panel, SkeletonRows, StatusBadge } from '../shared/ui'

export function OverviewPage() {
  const dashboard = useQuery({
    queryKey: ['overview-dashboard'],
    queryFn: () => api<OverviewDashboard>('/overview/dashboard'),
    refetchInterval: 30_000,
  })

  if (dashboard.isLoading) return <OverviewSkeleton />
  if (dashboard.error) return <ErrorState message={(dashboard.error as Error).message} retry={() => void dashboard.refetch()} />
  if (!dashboard.data) return null
  const data = dashboard.data

  return <div className="ops-page overview-page">
    <div className="overview-layout">
      <main className="overview-main">
        <Briefing data={data} />
        <div className="overview-kpi-grid" aria-label="Invoice work summary">
          {data.kpis.map((item, index) => <KpiCard key={item.id} item={item} index={index} />)}
          <Findings data={data} />
        </div>
        <DecisionQueue data={data} />
        <div className="overview-analytics">
          <Throughput data={data} />
          <ExceptionBreakdown data={data} />
          <Pipeline data={data} />
        </div>
      </main>
      <aside className="overview-rail">
        <Alerts alerts={data.alerts} />
        <RecentDecisions data={data} />
      </aside>
    </div>
    <footer className="overview-freshness">Data observed {formatDate(data.observed_at, true)}. Counts are calculated from the complete workspace, not the visible table page.</footer>
  </div>
}

function Briefing({ data }: { data: OverviewDashboard }) {
  return <Panel className="overview-briefing">
    <div className="overview-briefing-copy">
      <h1>{greeting()}, {firstName(data.actor.name)}</h1>
      <strong>{data.briefing.title}</strong>
      <p>{data.briefing.detail}</p>
      <Link className="ops-button ops-button--primary" to={data.briefing.action_href}>{data.briefing.action_label}<ArrowRight size={15} /></Link>
    </div>
    <div className="overview-briefing-mark" aria-hidden="true"><Sparkles size={24} /><strong>AI</strong></div>
  </Panel>
}

function KpiCard({ item, index }: { item: OverviewKpi; index: number }) {
  return <Link className={`ops-panel overview-kpi is-${item.tone}`} to={item.href} style={{ animationDelay: `${70 + index * 45}ms` }}>
    <span className="overview-kpi-icon">{kpiIcon(index, item.id)}</span>
    <strong>{item.count}</strong>
    <b>{item.label}</b>
    <small>{item.note}</small>
    <ChevronRight size={15} />
  </Link>
}

function Findings({ data }: { data: OverviewDashboard }) {
  return <Panel className="overview-findings" ariaLabel="Detected findings">
    <header><div><Sparkles size={16} /><h2>Detected findings</h2></div><span title="Counts come from stored extraction and validation evidence.">Evidence-based</span></header>
    <div>{data.findings.map((item, index) => <Link key={item.id} to={item.href}><span className={`is-${item.tone}`}>{findingIcon(index)}</span><b>{item.count}</b><small>{item.label}</small><ChevronRight size={13} /></Link>)}</div>
    <Link className="ops-link" to="/exceptions">Review all findings <ArrowRight size={13} /></Link>
  </Panel>
}

function Alerts({ alerts }: { alerts: OverviewAlert[] }) {
  return <Panel className="overview-alerts" ariaLabel="Priority alerts">
    <header><div><AlertTriangle size={17} /><h2>Priority alerts</h2></div><span>{alerts.length}</span></header>
    {alerts.length ? <div>{alerts.map((alert, index) => <Link key={alert.id} to={alert.href} className={`is-${alert.severity}`} style={{ animationDelay: `${110 + index * 55}ms` }}><span>{alert.severity === 'critical' ? <AlertCircle /> : alert.severity === 'warning' ? <TriangleAlert /> : <FileSearch />}</span><div><strong>{alert.title}</strong><small>{alert.detail}</small></div><ChevronRight size={15} /></Link>)}</div> : <div className="overview-healthy"><CheckCircle2 size={22} /><div><strong>No priority alerts</strong><small>Current records do not require immediate action.</small></div></div>}
  </Panel>
}

function DecisionQueue({ data }: { data: OverviewDashboard }) {
  return <Panel className="overview-queue" ariaLabel="Decision queue">
    <header><div><h2>Decision queue</h2><span>{data.queue.total}</span></div><Link className="ops-link" to="/review-queue">View full queue <ChevronRight size={13} /></Link></header>
    {data.queue.items.length ? <>
      <div className="ops-table-wrap overview-queue-table"><table className="ops-table"><thead><tr><th>Invoice</th><th>Vendor</th><th>Finding</th><th>Risk</th><th>Confidence</th><th>Due</th><th>Next action</th></tr></thead><tbody>{data.queue.items.map((item) => <QueueRow key={item.document_id} item={item} />)}</tbody></table></div>
      <div className="overview-queue-mobile">{data.queue.items.map((item) => <QueueCard key={item.document_id} item={item} />)}</div>
    </> : <EmptyState title="No invoices are waiting for review" body="Newly processed invoices will appear here when a reviewer decision is required." />}
  </Panel>
}

function QueueRow({ item }: { item: OverviewQueueItem }) {
  return <tr><td><Link className="ops-link" to={item.href}>{item.invoice_number}</Link><small>{formatMoney(item.total, item.currency)}</small></td><td>{item.vendor_name}</td><td className="overview-finding-cell">{item.risk === 'high' ? <AlertCircle /> : <TriangleAlert />}{item.finding}</td><td><RiskBadge risk={item.risk} /></td><td><Confidence value={item.confidence} /></td><td>{formatDate(item.due_date)}</td><td><Link className="overview-row-action" to={item.href}>{item.recommended_action === 'request_correction' ? 'Resolve' : 'Review'}<ChevronRight size={13} /></Link></td></tr>
}

function QueueCard({ item }: { item: OverviewQueueItem }) {
  return <Link to={item.href}><header><div><strong>{item.invoice_number}</strong><small>{item.vendor_name}</small></div><RiskBadge risk={item.risk} /></header><p>{item.finding}</p><footer><span>{formatMoney(item.total, item.currency)}</span><Confidence value={item.confidence} /><ChevronRight size={15} /></footer></Link>
}

function RiskBadge({ risk }: { risk: OverviewQueueItem['risk'] }) {
  return <StatusBadge tone={risk === 'high' ? 'danger' : risk === 'medium' ? 'warning' : 'info'}>{risk[0].toUpperCase() + risk.slice(1)}</StatusBadge>
}

function Confidence({ value }: { value: number | null }) {
  const percent = value == null ? null : Math.round(value * 100)
  return <span className="overview-confidence" title={percent == null ? 'Confidence was not recorded' : `${percent}% extraction confidence`}><span><i style={{ width: `${percent ?? 0}%` }} /></span><b>{percent == null ? '-' : `${percent}%`}</b></span>
}

function Throughput({ data }: { data: OverviewDashboard }) {
  const reduced = reducedMotion()
  return <Panel className="overview-throughput" ariaLabel="Processing throughput">
    <header><div><h2>Throughput</h2><p>{data.throughput.window_label}</p></div><div className="overview-chart-legend"><span className="is-processed">Processed</span><span className="is-review">Sent for review</span></div></header>
    <div className="overview-chart" role="img" aria-label={throughputLabel(data)}>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data.throughput.points} margin={{ top: 16, right: 12, left: -26, bottom: 0 }}>
          <CartesianGrid stroke="#edf1f5" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 9, fill: '#5c6a84' }} axisLine={false} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fontSize: 9, fill: '#5c6a84' }} axisLine={false} tickLine={false} />
          <Tooltip content={<ThroughputTooltip />} />
          <Area type="monotone" dataKey="processed" name="Processed" stroke="#00879b" fill="#dff3f4" strokeWidth={2.2} isAnimationActive={!reduced} animationDuration={600} />
          <Area type="monotone" dataKey="sent_for_review" name="Sent for review" stroke="#f07b18" fill="#fff0df" strokeWidth={2} isAnimationActive={!reduced} animationBegin={80} animationDuration={600} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
    <footer><span>{data.throughput.method}</span><Link className="ops-link" to="/invoices">View invoices <ChevronRight size={13} /></Link></footer>
  </Panel>
}

function ThroughputTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) {
  if (!active || !payload?.length) return null
  return <div className="overview-chart-tooltip"><strong>{label}</strong>{payload.map((item) => <span key={item.name}><i style={{ background: item.color }} />{item.name}<b>{item.value}</b></span>)}</div>
}

function ExceptionBreakdown({ data }: { data: OverviewDashboard }) {
  const categories = data.exception_breakdown.categories
  return <Panel className="overview-exceptions" ariaLabel="Exception breakdown">
    <header><h2>Exception breakdown</h2><Link className="ops-link" to="/exceptions">View all <ChevronRight size={13} /></Link></header>
    {categories.length ? <><div className="overview-donut" role="img" aria-label={`${data.exception_breakdown.total} open validation issues across ${categories.length} categories`}><ResponsiveContainer width="100%" height={150}><PieChart><Pie data={categories} dataKey="count" nameKey="label" innerRadius={43} outerRadius={62} paddingAngle={2} isAnimationActive={!reducedMotion()} animationDuration={550}>{categories.map((item) => <Cell key={item.id} fill={item.color} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer><div><strong>{data.exception_breakdown.total}</strong><span>Open issues</span></div></div><div className="overview-exception-list">{categories.map((item) => <Link key={item.id} to={item.href}><i style={{ background: item.color }} /><span>{item.label}</span><b>{item.count}</b><small>{item.percentage}%</small></Link>)}</div></> : <div className="overview-analytics-empty"><CheckCircle2 size={20} /><span>No open validation issues</span></div>}
  </Panel>
}

function Pipeline({ data }: { data: OverviewDashboard }) {
  return <Panel className="overview-pipeline" ariaLabel="Invoice pipeline">
    <header><h2>Pipeline summary</h2><Link className="ops-link" to="/invoices">View all <ChevronRight size={13} /></Link></header>
    <div>{data.pipeline.items.map((item, index) => <Link key={item.id} to={item.href}><span>{pipelineIcon(index)}</span><small>{item.label}</small><strong>{item.count}</strong><ChevronRight size={13} /></Link>)}</div>
    {data.pipeline.excluded_count ? <footer title={data.pipeline.note}>{data.pipeline.excluded_count} outside the main pipeline</footer> : null}
  </Panel>
}

function RecentDecisions({ data }: { data: OverviewDashboard }) {
  return <Panel className="overview-decisions" ariaLabel="Recent decisions">
    <header><h2>Recent decisions</h2><Link className="ops-link" to="/invoices?view=completed">View all</Link></header>
    {data.recent_decisions.length ? <div>{data.recent_decisions.map((item, index) => <Link key={item.id} to={item.href} style={{ animationDelay: `${180 + index * 45}ms` }}><span className={`is-${item.tone}`}>{decisionIcon(item.tone)}</span><div><strong>{item.title}</strong><small>{item.invoice}</small><small>{item.vendor}</small></div><aside><i>{initials(item.actor)}</i><time dateTime={item.occurred_at}>{relativeTime(item.occurred_at)}</time></aside></Link>)}</div> : <div className="overview-healthy"><Clock3 size={21} /><div><strong>No decisions recorded yet</strong><small>Approval, rejection, correction, and export events will appear here.</small></div></div>}
  </Panel>
}

function OverviewSkeleton() {
  return <div className="ops-page overview-page overview-skeleton"><div className="overview-layout"><main className="overview-main"><Panel><SkeletonRows count={3} /></Panel><div className="overview-kpi-grid">{Array.from({ length: 5 }, (_, index) => <Panel key={index}><SkeletonRows count={3} /></Panel>)}</div><Panel><SkeletonRows count={8} /></Panel><div className="overview-analytics"><Panel><SkeletonRows count={6} /></Panel><Panel><SkeletonRows count={6} /></Panel><Panel><SkeletonRows count={6} /></Panel></div></main><aside className="overview-rail"><Panel><SkeletonRows count={7} /></Panel><Panel><SkeletonRows count={7} /></Panel></aside></div></div>
}

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

function firstName(name: string) {
  return name.trim().split(/\s+/)[0] || 'there'
}

function initials(value: string) {
  return value.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
}

function relativeTime(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return 'Now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`
  return formatDate(value)
}

function pipelineIcon(index: number) {
  if (index === 0) return <Upload />
  if (index === 1) return <FileSearch />
  if (index === 2) return <Clock3 />
  if (index === 3) return <CircleCheckBig />
  return <FileCheck2 />
}

function kpiIcon(index: number, id: string) {
  if (index === 0) return <Clock3 />
  if (index === 1) return <AlertCircle />
  if (index === 2) return <CalendarDays />
  if (id === 'ready_export') return <Upload />
  return <CircleCheckBig />
}

function findingIcon(index: number) {
  if (index === 0) return <FileSearch />
  if (index === 1) return <ListChecks />
  return <TriangleAlert />
}

function decisionIcon(tone: string) {
  if (tone === 'success') return <CheckCircle2 />
  if (tone === 'danger') return <AlertCircle />
  if (tone === 'warning') return <TriangleAlert />
  return <FileCheck2 />
}

function throughputLabel(data: OverviewDashboard) {
  const summary = data.throughput.points.map((point) => `${point.label}: ${point.processed} processed, ${point.sent_for_review} sent for review`).join('. ')
  return summary || `No processing throughput was recorded for ${data.throughput.window_label.toLowerCase()}`
}

function reducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}
