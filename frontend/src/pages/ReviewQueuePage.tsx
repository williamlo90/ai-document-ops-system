import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertCircle, CalendarDays, ChevronRight, Clock3, FileSearch, ShieldAlert, X } from 'lucide-react'
import { api } from '../api/client'
import { PdfPreview } from '../components/PdfPreview'
import { formatDate, formatMoney, invoiceLabel } from '../features/invoices/format'
import type { InvoiceDetailResponse } from '../features/invoices/types'
import type { ReviewQueueItem, ReviewWorklist } from '../features/review/types'
import { Button, EmptyState, ErrorState, PageHeader, Panel, SearchField, SkeletonRows, StatusBadge } from '../shared/ui'

const pageSize = 10

export function ReviewQueuePage() {
  const [params, setParams] = useSearchParams()
  const search = params.get('search') ?? ''
  const risk = params.get('risk') ?? ''
  const vendor = params.get('vendor') ?? ''
  const owner = params.get('owner') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const sort = params.get('sort') ?? 'risk'
  const direction = params.get('direction') ?? 'desc'
  const selectedId = params.get('invoice')
  const request = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, direction })
  if (search) request.set('search', search)
  if (risk) request.set('risk', risk)
  if (vendor) request.set('vendor', vendor)
  if (owner) request.set('owner', owner)
  const queue = useQuery({ queryKey: ['review-worklist-v2', request.toString()], queryFn: () => api<ReviewWorklist>(`/review/worklist?${request}`), refetchInterval: 10_000 })
  const items = Array.isArray(queue.data?.items) ? queue.data.items : []
  const selected = items.find((item) => item.id === selectedId) ?? null
  const detail = useQuery({ queryKey: ['invoice-detail', selected?.id], queryFn: () => api<InvoiceDetailResponse>(`/documents/${selected?.id}`), enabled: Boolean(selected) })

  const filter = (key: string, value?: string) => updateParams(params, setParams, { [key]: value || null, page: null, ...(key !== 'invoice' ? { invoice: null } : {}) })
  const summary = queue.data?.summary

  return <div className="ops-page review-queue-page">
    <PageHeader title="Inbox" description="Review invoices that need a decision or have a blocking validation issue." />
    {queue.error ? <ErrorState message={(queue.error as Error).message} retry={() => void queue.refetch()} /> : <>
      <Panel className="review-kpis" ariaLabel="Review queue summary">
        <QueueMetric icon={<FileSearch size={23} />} value={summary?.in_queue ?? 0} label="In queue" tone="info" />
        <QueueMetric icon={<AlertCircle size={23} />} value={summary?.high_risk ?? 0} label="High risk" tone="danger" />
        <QueueMetric icon={<CalendarDays size={23} />} value={summary?.invoice_due_today ?? 0} label="Invoice due today" tone="warning" />
        <QueueMetric icon={<Clock3 size={23} />} value={summary?.average_review_seconds == null ? 'Not measured' : duration(summary.average_review_seconds)} label="Avg review time" tone="info" compact={summary?.average_review_seconds == null} />
      </Panel>
      <div className={`review-master-detail ${selected ? 'has-selection' : ''}`}>
        <Panel className="review-queue-list">
          <div className="review-filterbar">
            <div className="review-filter-search"><SearchField value={search} onChange={(value) => filter('search', value)} placeholder="Search invoices..." label="Search review queue" /></div>
            <select aria-label="Risk" value={risk} onChange={(event) => filter('risk', event.target.value)}><option value="">All risk</option><option value="high">High risk</option><option value="medium">Medium risk</option><option value="low">Low risk</option></select>
            <input className="ops-filter-input" aria-label="Vendor filter" value={vendor} onChange={(event) => filter('vendor', event.target.value)} placeholder="Vendor" />
            <input className="ops-filter-input" aria-label="Owner filter" value={owner} onChange={(event) => filter('owner', event.target.value)} placeholder="Owner" />
            <select aria-label="Sort review queue" value={`${sort}:${direction}`} onChange={(event) => { const [nextSort,nextDirection]=event.target.value.split(':'); updateParams(params,setParams,{sort:nextSort,direction:nextDirection,page:null}) }}><option value="risk:desc">Highest risk</option><option value="updated:asc">Oldest waiting</option><option value="due_date:asc">Invoice due date</option></select>
          </div>
          {queue.isLoading ? <SkeletonRows count={8} /> : items.length ? <ReviewTable items={items} selectedId={selected?.id} select={(id) => filter('invoice', id)} /> : <EmptyState title="No invoices need review" body="New invoices will appear here when a human decision is required." />}
          {queue.data ? <footer className="ops-pagination"><span>Showing page {queue.data.page} of {queue.data.total_pages} / {queue.data.total} invoices</span><div><Button variant="ghost" disabled={page <= 1} onClick={() => filter('page',String(page-1))}>Previous</Button><strong>{page}</strong><Button variant="ghost" disabled={page >= queue.data.total_pages} onClick={() => filter('page',String(page+1))}>Next</Button></div></footer> : null}
        </Panel>
        {selected ? <ReviewInspector item={selected} detail={detail.data} loading={detail.isLoading} error={detail.error as Error | null} close={() => filter('invoice')} /> : null}
      </div>
    </>}
  </div>
}

function QueueMetric({ icon, value, label, tone, compact }: { icon: React.ReactNode; value: React.ReactNode; label: string; tone: 'info'|'danger'|'warning'; compact?: boolean }) {
  return <div className="review-kpi"><span className={`ops-kpi__icon ops-tone-${tone}`}>{icon}</span><div><strong className={compact ? 'is-compact' : ''}>{value}</strong><span>{label}</span></div></div>
}

function ReviewTable({ items, selectedId, select }: { items: ReviewQueueItem[]; selectedId?: string; select: (id: string) => void }) {
  return <div className="ops-table-wrap"><table className="ops-table review-table"><thead><tr><th aria-label="Selected" /><th>Invoice</th><th>Vendor</th><th>Amount</th><th>Issue</th><th>Risk</th><th>Age</th><th>Owner</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className={selectedId === item.id ? 'is-selected' : ''} onClick={() => select(item.id)}><td><span className="ops-radio">{selectedId === item.id ? <i /> : null}</span></td><td><button className="ops-link" onClick={(event) => { event.stopPropagation(); select(item.id) }}>{invoiceLabel(item)}</button><small className="review-source-name">{item.original_filename}</small><small className="review-mobile-vendor">{item.vendor_name || 'Vendor not detected'}</small></td><td>{item.vendor_name || '-'}</td><td>{formatMoney(item.total,item.currency)}</td><td className={item.finding ? 'review-finding' : ''}>{item.finding || 'No validation issue'}</td><td><StatusBadge tone={riskTone(item.risk)}>{item.risk[0].toUpperCase()+item.risk.slice(1)}</StatusBadge></td><td>{age(item.age_seconds)}</td><td><span className="ops-owner"><i>{initials(item.owner)}</i>{item.owner}</span></td></tr>)}</tbody></table></div>
}

function ReviewInspector({ item, detail, loading, error, close }: { item: ReviewQueueItem; detail?: InvoiceDetailResponse; loading: boolean; error: Error | null; close: () => void }) {
  const data = detail?.extraction?.data
  const issues = detail?.extraction?.validation ?? []
  return <Panel className="review-inspector" ariaLabel="Selected invoice review summary"><header><div><span>{invoiceLabel(item)}</span><StatusBadge tone={riskTone(item.risk)}>{item.risk[0].toUpperCase()+item.risk.slice(1)} risk</StatusBadge><strong>{item.vendor_name || 'Vendor not detected'} / {formatMoney(item.total,item.currency)}</strong></div><button className="ops-icon-button" aria-label="Close review summary" onClick={close}><X size={19} /></button></header>{error ? <ErrorState message={error.message} /> : loading ? <SkeletonRows count={6} /> : <div className="review-inspector-content"><section><div className="review-section-heading"><h3>Extracted data</h3></div><dl className="review-field-list"><Field label="Invoice number" value={data?.invoice_number} /><Field label="Vendor" value={data?.vendor_name} /><Field label="Invoice date" value={formatDate(data?.invoice_date)} /><Field label="Due date" value={formatDate(data?.due_date)} /><Field label="Total amount" value={formatMoney(data?.total,data?.currency)} /></dl></section><section className={`review-finding-card ${item.blocker_count ? 'is-blocker' : ''}`}><header><ShieldAlert size={17} /><strong>Validation issue</strong></header><h3>{item.finding || 'No validation issue'}</h3><p>{item.blocker_count ? 'Approval is blocked until this issue is corrected and validation passes.' : item.issue_count ? 'Review the invoice and stored evidence before deciding.' : 'No validation blocker is currently recorded.'}</p>{issues.slice(0,3).map((issue) => <div key={issue.code}><ShieldAlert size={13} />{issue.message}</div>)}</section><div className="review-preview"><PdfPreview url={`/documents/${item.id}/content`} filename={item.original_filename} /></div><section className="review-recommendation"><ShieldAlert size={17} /><div><strong>Required action</strong><p>{item.recommended_action === 'request_correction' ? 'Request a correction because validation blockers remain.' : 'Open the invoice workspace and record a reviewer decision.'}</p></div></section><Link className="ops-button ops-button--primary review-open" to={`/review/${item.id}`}><span>Review invoice</span><ChevronRight size={16} /></Link></div>}</Panel>
}

function Field({ label, value }: { label: string; value?: string | null }) { const missing=!value||value==='-'; return <div className={missing?'is-missing':''}><dt>{label}</dt><dd>{missing?'Missing':value}</dd></div> }
function riskTone(value: ReviewQueueItem['risk']): 'danger'|'warning'|'info' { return value==='high'?'danger':value==='medium'?'warning':'info' }
function age(seconds:number):string { if(seconds<3600)return `${Math.max(1,Math.floor(seconds/60))}m`; if(seconds<86400)return `${Math.floor(seconds/3600)}h`; return `${Math.floor(seconds/86400)}d` }
function duration(seconds:number):string { return seconds<60?`${Math.round(seconds)}s`:`${Math.round(seconds/60)}m` }
function initials(value:string):string { return value.split(/\s+/).filter(Boolean).map((part)=>part[0]).join('').slice(0,2).toUpperCase()||'RV' }
function updateParams(current:URLSearchParams,setter:ReturnType<typeof useSearchParams>[1],values:Record<string,string|null|undefined>){const next=new URLSearchParams(current);for(const [key,value] of Object.entries(values)){if(value)next.set(key,value);else next.delete(key)}setter(next)}
