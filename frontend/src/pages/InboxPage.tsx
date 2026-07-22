import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowRight, CalendarDays, CheckCircle2, Clock3, Inbox as InboxIcon } from 'lucide-react'
import { api } from '../api/client'
import type { ExceptionCategory, ExceptionItem, ExceptionListResponse } from '../features/exceptions/types'
import { formatMoney, invoiceLabel } from '../features/invoices/format'
import type { ReviewQueueItem, ReviewWorklist } from '../features/review/types'
import { Button, EmptyState, ErrorState, PageHeader, Panel, SearchField, SkeletonRows, StatusBadge } from '../shared/ui'

const pageSize = 12
const categoryLabels: Record<ExceptionCategory, string> = {
  vendor_invoice: 'Vendor or invoice',
  tax_amount: 'Tax or amount',
  duplicate: 'Duplicate',
  dates_details: 'Dates or details',
  other: 'Other',
}

export function InboxPage() {
  const [params, setParams] = useSearchParams()
  const state = params.get('state') === 'blocked' ? 'blocked' : 'needs-decision'
  const search = params.get('search') ?? ''
  const risk = params.get('risk') ?? ''
  const owner = params.get('owner') ?? ''
  const vendor = params.get('vendor') ?? ''
  const category = params.get('category') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const sort = params.get('sort') ?? (state === 'blocked' ? 'risk' : 'risk')
  const direction = params.get('direction') ?? 'desc'

  const reviewRequest = new URLSearchParams({ page: String(state === 'needs-decision' ? page : 1), page_size: String(pageSize), sort, direction })
  if (search && state === 'needs-decision') reviewRequest.set('search', search)
  if (risk && state === 'needs-decision') reviewRequest.set('risk', risk)
  if (owner && state === 'needs-decision') reviewRequest.set('owner', owner)
  if (vendor && state === 'needs-decision') reviewRequest.set('vendor', vendor)

  const exceptionRequest = new URLSearchParams({ page: String(state === 'blocked' ? page : 1), page_size: String(pageSize), scope: 'blocking', sort, direction })
  if (search && state === 'blocked') exceptionRequest.set('search', search)
  if (risk && state === 'blocked') exceptionRequest.set('risk', risk)
  if (owner && state === 'blocked') exceptionRequest.set('owner', owner)
  if (category && state === 'blocked') exceptionRequest.set('category', category)

  const review = useQuery({ queryKey: ['review-worklist-v2', reviewRequest.toString()], queryFn: () => api<ReviewWorklist>(`/review/worklist?${reviewRequest}`), refetchInterval: 10_000 })
  const blocked = useQuery({ queryKey: ['exceptions', exceptionRequest.toString()], queryFn: () => api<ExceptionListResponse>(`/exceptions?${exceptionRequest}`), refetchInterval: 10_000 })
  const current = state === 'blocked' ? blocked : review
  const setFilter = (values: Record<string, string | null | undefined>) => updateParams(params, setParams, { ...values, page: null })
  const selectState = (value: 'needs-decision' | 'blocked') => updateParams(params, setParams, { state: value, search: null, risk: null, owner: null, vendor: null, category: null, sort: 'risk', direction: 'desc', page: null })

  return <div className="ops-page inbox-page">
    <PageHeader title="Inbox" description="Resolve the invoices that are waiting on a reviewer or blocked by validation." />
    <div className="inbox-summary" aria-label="Inbox summary" tabIndex={0}>
      <Summary icon={<InboxIcon size={19} />} value={review.data?.summary.in_queue ?? 0} label="Needs decision" />
      <Summary icon={<AlertCircle size={19} />} value={blocked.data?.summary.open_exceptions ?? 0} label="Blocking issues" tone="danger" />
      <Summary icon={<CalendarDays size={19} />} value={review.data?.summary.invoice_due_today ?? 0} label="Due today" tone="warning" />
    </div>
    <Panel className="inbox-worklist">
      <div className="inbox-tabs" role="tablist" aria-label="Inbox state">
        <button role="tab" aria-selected={state === 'needs-decision'} className={state === 'needs-decision' ? 'is-active' : ''} onClick={() => selectState('needs-decision')}>Needs decision <span>{review.data?.total ?? 0}</span></button>
        <button role="tab" aria-selected={state === 'blocked'} className={state === 'blocked' ? 'is-active' : ''} onClick={() => selectState('blocked')}>Blocked <span>{blocked.data?.total ?? 0}</span></button>
      </div>
      <div className="inbox-toolbar">
        <SearchField value={search} onChange={(value) => setFilter({ search: value || null })} placeholder={state === 'blocked' ? 'Search blocked invoices' : 'Search invoices'} label="Search inbox" />
        <select aria-label="Risk" value={risk} onChange={(event) => setFilter({ risk: event.target.value || null })}><option value="">All risk</option><option value="high">High risk</option><option value="medium">Medium risk</option>{state === 'needs-decision' ? <option value="low">Low risk</option> : null}</select>
        {state === 'blocked' ? <select aria-label="Issue type" value={category} onChange={(event) => setFilter({ category: event.target.value || null })}><option value="">All issue types</option>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select> : <input className="ops-filter-input" aria-label="Vendor" value={vendor} onChange={(event) => setFilter({ vendor: event.target.value || null })} placeholder="Vendor" />}
        <input className="ops-filter-input" aria-label="Owner" value={owner} onChange={(event) => setFilter({ owner: event.target.value || null })} placeholder="Owner" />
        <select aria-label="Sort inbox" value={`${sort}:${direction}`} onChange={(event) => { const [nextSort, nextDirection] = event.target.value.split(':'); setFilter({ sort: nextSort, direction: nextDirection }) }}><option value="risk:desc">Highest risk</option><option value="updated:asc">Oldest waiting</option></select>
      </div>
      {current.error ? <ErrorState message={state === 'blocked' ? 'Blocked invoices could not be loaded.' : 'Invoices awaiting a decision could not be loaded.'} retry={() => void current.refetch()} /> : current.isLoading ? <SkeletonRows count={8} /> : state === 'blocked' ? <BlockedTable items={blocked.data?.items ?? []} /> : <DecisionTable items={review.data?.items ?? []} />}
      {current.data ? <Pagination page={current.data.page} pages={current.data.total_pages} total={current.data.total} setPage={(value) => setFilter({ page: String(value) })} /> : null}
    </Panel>
  </div>
}

function Summary({ icon, value, label, tone = 'neutral' }: { icon: React.ReactNode; value: number; label: string; tone?: 'neutral' | 'warning' | 'danger' }) {
  return <div className={`inbox-summary-item is-${tone}`}><span>{icon}</span><strong>{value}</strong><small>{label}</small></div>
}

function DecisionTable({ items }: { items: ReviewQueueItem[] }) {
  if (!items.length) return <EmptyState title="No invoices need a decision" body="Invoices will appear here when validation finishes and a reviewer decision is required." />
  return <div className="ops-table-wrap"><table className="ops-table inbox-table"><thead><tr><th>Invoice</th><th>Vendor</th><th>Amount</th><th>Issue</th><th>Risk</th><th>Waiting</th><th>Owner</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{invoiceLabel(item)}</strong><small>{item.original_filename}</small></td><td>{item.vendor_name || 'Not detected'}</td><td>{formatMoney(item.total, item.currency)}</td><td>{item.finding || <span className="inbox-clear"><CheckCircle2 size={14} /> No blocker</span>}</td><td><Risk risk={item.risk} /></td><td><Clock3 size={13} /> {age(item.age_seconds)}</td><td>{item.owner || 'Unassigned'}</td><td><Link className="ops-button ops-button--secondary" to={`/review/${item.id}?from=inbox`}>Review <ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>
}

function BlockedTable({ items }: { items: ExceptionItem[] }) {
  if (!items.length) return <EmptyState title="No blocked invoices" body="Approval blockers will appear here with the validation issue that must be resolved." />
  return <div className="ops-table-wrap"><table className="ops-table inbox-table"><thead><tr><th>Issue</th><th>Invoice</th><th>Vendor</th><th>Risk</th><th>Waiting</th><th>Owner</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong className="inbox-issue"><AlertCircle size={14} />{item.issue}</strong><small>{categoryLabels[item.category]}</small></td><td>{item.invoice_number || item.original_filename}</td><td>{item.vendor_name || 'Not detected'}</td><td><Risk risk={item.risk} /></td><td><Clock3 size={13} /> {age(item.age_seconds)}</td><td>{item.owner || 'Unassigned'}</td><td><Link className="ops-button ops-button--secondary" to={`/review/${item.document_id}?from=inbox&state=blocked&exception=${item.id}`}>Resolve <ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div>
}

function Risk({ risk }: { risk: 'high' | 'medium' | 'low' }) {
  return <StatusBadge tone={risk === 'high' ? 'danger' : risk === 'medium' ? 'warning' : 'info'}>{risk[0].toUpperCase() + risk.slice(1)}</StatusBadge>
}

function Pagination({ page, pages, total, setPage }: { page: number; pages: number; total: number; setPage: (page: number) => void }) {
  return <footer className="ops-pagination"><span>{total} result{total === 1 ? '' : 's'}</span><div><Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><strong>{page} / {pages}</strong><Button variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div></footer>
}

function age(seconds: number): string { if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))}m`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`; return `${Math.floor(seconds / 86400)}d` }
function updateParams(current: URLSearchParams, setter: ReturnType<typeof useSearchParams>[1], values: Record<string, string | null | undefined>) { const next = new URLSearchParams(current); for (const [key, value] of Object.entries(values)) { if (value) next.set(key, value); else next.delete(key) } setter(next) }
