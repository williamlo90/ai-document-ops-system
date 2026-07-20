import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Copy,
  Download,
  FileWarning,
  LoaderCircle,
  Search,
  Sparkles,
  UserRoundPlus,
  X,
} from 'lucide-react'
import { api } from '../api/client'
import type {
  ExceptionAssignmentResponse,
  ExceptionCategory,
  ExceptionDetail,
  ExceptionDetailResponse,
  ExceptionItem,
  ExceptionListResponse,
} from '../features/exceptions/types'
import { formatMoney } from '../features/invoices/format'
import { queryClient } from '../queryClient'
import { Button, EmptyState, ErrorState, PageHeader, Panel, SkeletonRows, StatusBadge } from '../shared/ui'

const pageSize = 10
const emptyExceptionItems: ExceptionItem[] = []
const categoryLabels: Record<ExceptionCategory, string> = {
  vendor_invoice: 'Vendor / invoice',
  tax_amount: 'Tax / amount',
  duplicate: 'Duplicate',
  dates_details: 'Dates / details',
  other: 'Other',
}

export function ExceptionsPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const search = params.get('search') ?? ''
  const scope = params.get('scope') ?? 'all'
  const category = params.get('category') ?? ''
  const risk = params.get('risk') ?? ''
  const owner = params.get('owner') ?? ''
  const sort = params.get('sort') ?? 'risk'
  const direction = params.get('direction') ?? 'desc'
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const selectedId = params.get('exception')
  const [searchDraft, setSearchDraft] = useState(search)
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignee, setAssignee] = useState('')
  const [toast, setToast] = useState('')
  const listTop = useRef<HTMLDivElement>(null)

  useEffect(() => setSearchDraft(search), [search])
  useEffect(() => {
    if (searchDraft === search) return
    const timer = window.setTimeout(() => updateParams(params, setParams, { search: searchDraft || null, page: null, exception: null }), 250)
    return () => window.clearTimeout(timer)
  }, [params, search, searchDraft, setParams])
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 2600)
    return () => window.clearTimeout(timer)
  }, [toast])

  const request = buildRequest({ search, scope, category, risk, owner, sort, direction, page: String(page), page_size: String(pageSize) })
  const exceptions = useQuery({
    queryKey: ['exceptions', request.toString()],
    queryFn: () => api<ExceptionListResponse>(`/exceptions?${request}`),
    refetchInterval: 10_000,
  })
  const items = exceptions.data?.items ?? emptyExceptionItems
  const details = useQuery({
    queryKey: ['exception-detail', selectedId],
    queryFn: () => api<ExceptionDetailResponse>(`/exceptions/${selectedId}`),
    enabled: Boolean(selectedId),
  })

  useEffect(() => {
    if (!selectedId && items[0] && window.innerWidth >= 1280) {
      updateParams(params, setParams, { exception: items[0].id })
    }
  }, [items, params, selectedId, setParams])

  const assign = useMutation({
    mutationFn: (value: string) => api<ExceptionAssignmentResponse>(`/exceptions/${selectedId}/assignment`, {
      method: 'PATCH',
      body: JSON.stringify({ assignee: value || null }),
    }),
    onSuccess: (result) => {
      setAssignOpen(false)
      setToast(result.assignment.assignee ? `Assigned to ${result.assignment.assignee}` : 'Exception is now unassigned')
      queryClient.setQueryData(['exception-detail', selectedId], { exception: result.exception })
      void queryClient.invalidateQueries({ queryKey: ['exceptions'] })
    },
  })

  const filter = (values: Record<string, string | null>) => updateParams(params, setParams, { ...values, page: null, exception: null })
  const choose = (id: string) => updateParams(params, setParams, { exception: id })
  const selectedDetail = details.data?.exception

  async function download(allOpen: boolean) {
    setExportOpen(false)
    setExporting(true)
    try {
      const query = allOpen ? new URLSearchParams({ scope: 'all' }) : buildRequest({ search, scope, category, risk, owner })
      const response = await fetch(`/exceptions/export?${query}`, { credentials: 'same-origin' })
      if (!response.ok) throw new Error('The exception list could not be exported.')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'open-exceptions.csv'
      anchor.click()
      URL.revokeObjectURL(url)
      setToast('Exception list exported')
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : 'The exception list could not be exported.')
    } finally {
      setExporting(false)
    }
  }

  function moveSelection(event: KeyboardEvent<HTMLDivElement>) {
    if (!items.length || !['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) return
    event.preventDefault()
    const current = Math.max(0, items.findIndex((item) => item.id === selectedId))
    if (event.key === 'Enter') {
      const item = items[current]
      if (item) navigate(`/review/${item.document_id}?from=exceptions&exception=${item.id}`)
      return
    }
    if (event.key === ' ') {
      choose(items[current].id)
      return
    }
    const offset = event.key === 'ArrowDown' ? 1 : -1
    const next = items[Math.min(items.length - 1, Math.max(0, current + offset))]
    choose(next.id)
  }

  return <div className="exceptions-page">
    <div className={`exception-page-layout ${selectedId ? 'has-selection' : ''}`}>
      <div className="ops-page exception-primary">
        <PageHeader title="Exceptions" description="Resolve issues that are blocking invoice processing." action={<div className="exception-export-wrap">
          <Button onClick={() => setExportOpen((value) => !value)} disabled={exporting}><Download size={16} />{exporting ? 'Preparing export...' : 'Export list'}<ChevronDown size={14} /></Button>
          {exportOpen ? <div className="exception-export-menu" role="menu"><button role="menuitem" onClick={() => void download(false)}>Export current view</button><button role="menuitem" onClick={() => void download(true)}>Export all open exceptions</button></div> : null}
        </div>} />
        {exceptions.error ? <ErrorState message={(exceptions.error as Error).message} retry={() => void exceptions.refetch()} /> : <>
          {exceptions.isLoading ? <SkeletonRows count={8} /> : <>
            <ExceptionInsight summary={exceptions.data?.summary} filterCategory={(value) => filter({ category: value })} />
            <div className="exception-kpis" aria-label="Exception workload summary">
              <ExceptionMetric icon={<FileWarning />} value={exceptions.data?.summary.open_exceptions ?? 0} label="Open exceptions" tone="info" />
              <ExceptionMetric icon={<CircleAlert />} value={exceptions.data?.summary.high_risk ?? 0} label="High risk" tone="danger" />
              <ExceptionMetric icon={<AlertTriangle />} value={exceptions.data?.summary.warning_issues ?? 0} label="Warnings" tone="warning" />
              <ExceptionMetric icon={<FileWarning />} value={exceptions.data?.summary.invoices_affected ?? 0} label="Invoices affected" tone="success" />
            </div>
            <CategoryStrip counts={exceptions.data?.summary.categories ?? {}} active={category} select={(value) => filter({ category: value || null })} />
            <div className="exception-list-wrap" ref={listTop}>
              <Panel className="exception-list-panel">
                <div className="exception-toolbar">
                  <label className="ops-search"><span className="sr-only">Search exceptions</span><Search size={17} /><input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape') setSearchDraft('') }} placeholder="Search exceptions..." />{searchDraft ? <button type="button" onClick={() => setSearchDraft('')} aria-label="Clear search"><X size={15} /></button> : null}</label>
                  <div className="ops-segments" aria-label="Exception scope">{(['all','blocking','warnings'] as const).map((value) => <button key={value} className={scope === value ? 'is-active' : ''} onClick={() => filter({ scope: value })}>{value === 'all' ? 'All issues' : value === 'blocking' ? 'Blockers' : 'Warnings'}</button>)}</div>
                  <select aria-label="Issue type" value={category} onChange={(event) => filter({ category: event.target.value || null })}><option value="">Issue type</option>{Object.entries(categoryLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
                  <select aria-label="Risk" value={risk} onChange={(event) => filter({ risk: event.target.value || null })}><option value="">All risk</option><option value="high">High risk</option><option value="medium">Medium risk</option></select>
                  <select aria-label="Owner" value={owner} onChange={(event) => filter({ owner: event.target.value || null })}><option value="">All owners</option><option value="Unassigned">Unassigned</option>{exceptions.data?.assignee_options.map((value) => <option key={value} value={value}>{value}</option>)}</select>
                  <select aria-label="Sort exceptions" value={`${sort}:${direction}`} onChange={(event) => { const [nextSort,nextDirection]=event.target.value.split(':'); updateParams(params,setParams,{sort:nextSort,direction:nextDirection,page:null}) }}><option value="risk:desc">Highest risk</option><option value="age:desc">Oldest first</option><option value="updated:desc">Newest first</option><option value="issue:asc">Issue A-Z</option></select>
                </div>
                {items.length ? <ExceptionTable items={items} selectedId={selectedId} select={choose} onKeyDown={moveSelection} /> : <EmptyState title="No exceptions found" body="There are no exceptions matching the current filters." action={<Button onClick={() => filter({ search: null, scope: 'all', category: null, risk: null, owner: null })}>Clear filters</Button>} />}
                {exceptions.data ? <footer className="ops-pagination"><span>Showing {exceptions.data.total ? (page-1)*pageSize+1 : 0} to {Math.min(page*pageSize,exceptions.data.total)} of {exceptions.data.total} exceptions</span><div><Button variant="ghost" disabled={page <= 1} onClick={() => { updateParams(params,setParams,{page:String(page-1),exception:null}); listTop.current?.scrollIntoView({behavior:'smooth'}) }}>Previous</Button><strong>{page}</strong><Button variant="ghost" disabled={page >= exceptions.data.total_pages} onClick={() => { updateParams(params,setParams,{page:String(page+1),exception:null}); listTop.current?.scrollIntoView({behavior:'smooth'}) }}>Next</Button></div></footer> : null}
              </Panel>
            </div>
          </>}
        </>}
      </div>
      {selectedId ? <ExceptionInspector detail={selectedDetail} loading={details.isLoading} error={details.error as Error | null} close={() => updateParams(params,setParams,{exception:null})} assign={() => { setAssignee(selectedDetail?.owner ?? ''); setAssignOpen(true) }} /> : null}
    </div>
    {assignOpen && selectedDetail ? <AssignmentDialog detail={selectedDetail} value={assignee} options={exceptions.data?.assignee_options ?? []} setValue={setAssignee} pending={assign.isPending} error={assign.error as Error | null} close={() => setAssignOpen(false)} submit={() => assign.mutate(assignee)} /> : null}
    {toast ? <div className="ops-toast" role="status"><CheckCircle2 size={18} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={15} /></button></div> : null}
  </div>
}

function ExceptionInsight({ summary, filterCategory }: { summary?: ExceptionListResponse['summary']; filterCategory: (value: string) => void }) {
  const top = summary?.top_issues ?? []
  const highRisk = summary?.high_risk ?? 0
  return <Panel className="exception-insight" ariaLabel="Exception workload insight"><span className="exception-insight-icon"><Sparkles size={21} /></span><div><strong>{highRisk} high-risk {highRisk === 1 ? 'exception requires' : 'exceptions require'} review</strong><p>{highRisk ? 'These issues block approval until invoice data is corrected and validation passes.' : 'No approval-blocking validation issues are in the current view.'}</p></div><section><span>Top issue types</span><div>{top.length ? top.map((item) => <button key={item.label} onClick={() => filterCategory(item.category)}><i />{item.label}<b>{item.count}</b></button>) : <small>No issue pattern in this view</small>}</div></section></Panel>
}

function ExceptionMetric({ icon, value, label, tone }: { icon: React.ReactNode; value: number; label: string; tone: 'info'|'danger'|'warning'|'success' }) {
  return <Panel className={`exception-kpi is-${tone}`}><span className={`ops-kpi__icon ops-tone-${tone}`}>{icon}</span><div><strong>{value}</strong><span>{label}</span></div></Panel>
}

function CategoryStrip({ counts, active, select }: { counts: Partial<Record<ExceptionCategory,number>>; active: string; select: (value: string) => void }) {
  return <Panel className="exception-categories" ariaLabel="Exception categories">{(Object.keys(categoryLabels) as ExceptionCategory[]).map((value) => <button key={value} className={active === value ? 'is-active' : ''} onClick={() => select(active === value ? '' : value)}><i className={`is-${value}`} />{categoryLabels[value]}<strong>{counts[value] ?? 0}</strong></button>)}</Panel>
}

function ExceptionTable({ items, selectedId, select, onKeyDown }: { items: ExceptionItem[]; selectedId: string | null; select: (id: string) => void; onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void }) {
  return <div className="ops-table-wrap exception-table-wrap" tabIndex={0} onKeyDown={onKeyDown} aria-label="Exception list"><table className="ops-table exception-table"><thead><tr><th>Issue</th><th>Invoice</th><th>Vendor</th><th>Risk</th><th>Owner</th><th>Age</th><th>Action</th></tr></thead><tbody>{items.map((item) => <tr key={item.id} className={selectedId === item.id ? 'is-selected' : ''} onClick={() => select(item.id)}><td><span className={`exception-issue-icon is-${item.risk}`}>{item.blocks_approval ? <AlertCircle size={15} /> : <AlertTriangle size={15} />}</span><strong>{item.issue}</strong></td><td><button className="ops-link" onClick={(event) => { event.stopPropagation(); select(item.id) }}>{exceptionInvoiceLabel(item)}</button></td><td>{item.vendor_name || 'Vendor not detected'}</td><td><StatusBadge tone={item.risk === 'high' ? 'danger' : 'warning'}>{item.risk === 'high' ? 'High' : 'Medium'}</StatusBadge></td><td><span className="ops-owner"><i>{initials(item.owner)}</i>{item.owner || 'Unassigned'}</span></td><td>{age(item.age_seconds)}</td><td><Link className="exception-row-action" to={`/review/${item.document_id}?from=exceptions&exception=${item.id}`} onClick={(event) => event.stopPropagation()}>{item.blocks_approval ? 'Resolve' : 'Investigate'}<ChevronDown size={13} /></Link></td></tr>)}</tbody></table></div>
}

function ExceptionInspector({ detail, loading, error, close, assign }: { detail?: ExceptionDetail; loading: boolean; error: Error | null; close: () => void; assign: () => void }) {
  const [copied, setCopied] = useState(false)
  if (error) return <Panel className="exception-inspector" ariaLabel="Exception details"><button className="ops-icon-button exception-inspector-close" onClick={close} aria-label="Close exception details"><X size={18} /></button><ErrorState message="Exception details are unavailable. The exception list is still available." /></Panel>
  if (loading || !detail) return <Panel className="exception-inspector" ariaLabel="Exception details"><SkeletonRows count={7} /></Panel>
  const invoiceNumber = exceptionInvoiceLabel(detail)
  async function copyInvoice() { await navigator.clipboard?.writeText(invoiceNumber); setCopied(true); window.setTimeout(() => setCopied(false),1200) }
  return <Panel className="exception-inspector" ariaLabel="Exception details"><header><div><span>Exception details</span><h2>{invoiceNumber}</h2><p>{detail.vendor_name || 'Vendor not detected'} <i /> {formatMoney(detail.total,detail.currency)}</p></div><StatusBadge tone={detail.risk === 'high' ? 'danger' : 'warning'}>{detail.risk === 'high' ? 'High risk' : 'Medium risk'}</StatusBadge><button className="ops-icon-button exception-inspector-close" onClick={close} aria-label="Close exception details"><X size={18} /></button></header><div className="exception-detail-content"><section><h3>What happened</h3><p>{detail.message}</p>{detail.blocks_approval ? <div className="exception-block-alert"><AlertCircle size={16} />Approval is blocked until this issue is resolved.</div> : null}</section><section><h3>What is required</h3><p>{detail.required_action}</p></section><section><h3>Detected data</h3><dl className="exception-detected"><div><dt>Affected field</dt><dd>{fieldLabel(detail.field_name)}</dd></div><div><dt>Detected value</dt><dd className={!detail.field_value ? 'is-missing' : ''}>{detail.field_value || 'Missing'}</dd></div><div><dt>Invoice number</dt><dd><button onClick={() => void copyInvoice()}>{invoiceNumber}<Copy size={12} /></button>{copied ? <small>Copied</small> : null}</dd></div><div><dt>Vendor</dt><dd>{detail.vendor_name || 'Not detected'}</dd></div><div><dt>Total amount</dt><dd>{formatMoney(detail.total,detail.currency)}</dd></div></dl></section><section><h3>Related checks</h3><div className="exception-checks">{detail.related_checks.map((check) => <div key={`${check.label}-${check.status}`} className={`is-${check.status}`}>{check.status === 'passed' ? <CheckCircle2 size={16} /> : check.status === 'blocked' ? <AlertCircle size={16} /> : <AlertTriangle size={16} />}<span>{check.label}</span><StatusBadge tone={check.status === 'passed' ? 'success' : check.status === 'blocked' ? 'danger' : 'warning'}>{check.status === 'passed' ? 'Passed' : check.status === 'blocked' ? 'Blocked' : 'Warning'}</StatusBadge></div>)}</div></section><div className="exception-meta"><Clock3 size={14} />Detected {age(detail.age_seconds)} ago <i /> Owner {detail.owner || 'Unassigned'}</div></div><footer><Link className="ops-button ops-button--primary" to={`/review/${detail.document_id}?from=exceptions&exception=${detail.id}`}>Open invoice<ArrowUpRight size={16} /></Link><Button onClick={assign}><UserRoundPlus size={16} />Assign</Button></footer></Panel>
}

function AssignmentDialog({ detail, value, options, setValue, pending, error, close, submit }: { detail: ExceptionDetail; value: string; options: string[]; setValue: (value:string)=>void; pending:boolean; error:Error|null; close:()=>void; submit:()=>void }) {
  return <div className="ops-modal-backdrop" role="presentation" onMouseDown={(event) => { if(event.target===event.currentTarget)close() }}><section className="ops-modal exception-assignment-modal" role="dialog" aria-modal="true" aria-labelledby="exception-assignment-title"><header><div><h2 id="exception-assignment-title">Assign exception</h2><p>{detail.issue} / {exceptionInvoiceLabel(detail)}</p></div><button className="ops-icon-button" onClick={close} aria-label="Close assignment"><X size={18} /></button></header><div><label><span>Owner</span><input autoFocus value={value} onChange={(event)=>setValue(event.target.value)} list="exception-owner-options" placeholder="Name or leave blank for unassigned" /></label><datalist id="exception-owner-options">{options.map((option)=><option key={option} value={option} />)}</datalist>{error ? <p className="review-inline-error"><AlertCircle size={14} />{error.message}</p> : null}</div><footer><Button variant="ghost" onClick={close}>Cancel</Button><Button variant="primary" disabled={pending} onClick={submit}>{pending ? <LoaderCircle className="spin" size={15} /> : <UserRoundPlus size={15} />}Save assignment</Button></footer></section></div>
}

function buildRequest(values: Record<string,string>) { const request=new URLSearchParams(); Object.entries(values).forEach(([key,value])=>{if(value)request.set(key,value)}); return request }
function updateParams(current:URLSearchParams,setter:ReturnType<typeof useSearchParams>[1],values:Record<string,string|null|undefined>){const next=new URLSearchParams(current);for(const [key,value] of Object.entries(values)){if(value)next.set(key,value);else next.delete(key)}setter(next)}
function age(seconds:number){if(seconds<3600)return `${Math.max(1,Math.floor(seconds/60))}m`;if(seconds<86400)return `${Math.floor(seconds/3600)}h`;return `${Math.floor(seconds/86400)}d`}
function initials(value:string|null){return (value||'Unassigned').split(/\s+/).filter(Boolean).map((part)=>part[0]).join('').slice(0,2).toUpperCase()}
function fieldLabel(value:string){return value.replace(/_/g,' ').replace(/\[(\d+)\]/g,' $1')}
function exceptionInvoiceLabel(value:Pick<ExceptionItem,'invoice_number'|'original_filename'>){return value.invoice_number || value.original_filename}
