import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, Clock3, FileCheck2, FileText, MoreVertical, Sparkles, Upload, X } from 'lucide-react'
import { api, upload } from '../api/client'
import { useShell } from '../app/shell-context'
import { PdfPreview } from '../components/PdfPreview'
import { formatDate, formatMoney, invoiceLabel, invoiceStatus } from '../features/invoices/format'
import type { InvoiceDetailResponse, InvoiceItem, InvoiceListResponse } from '../features/invoices/types'
import { Button, EmptyState, ErrorState, KpiCard, PageHeader, Panel, SearchField, SkeletonRows, StatusBadge } from '../shared/ui'

const pageSize = 10

export function InvoicesPage() {
  const { role } = useShell()
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [uploadOpen, setUploadOpen] = useState(false)
  const search = params.get('search') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const status = params.get('status') ?? ''
  const view = params.get('view') ?? 'all'
  const vendor = params.get('vendor') ?? ''
  const sort = params.get('sort') ?? 'updated'
  const direction = params.get('direction') ?? 'desc'
  const selectedId = params.get('invoice')
  const requestStatus = status || (view === 'all' ? '' : view)
  const queryString = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, direction })
  if (search) queryString.set('search', search)
  if (requestStatus) queryString.set('status', requestStatus)
  if (vendor) queryString.set('vendor', vendor)
  const invoices = useQuery({ queryKey: ['invoices', queryString.toString()], queryFn: () => api<InvoiceListResponse>(`/invoices?${queryString}`), refetchInterval: 10_000 })
  const selected = invoices.data?.items.find((invoice) => invoice.id === selectedId) ?? null
  const detail = useQuery({ queryKey: ['invoice-detail', selected?.id], queryFn: () => api<InvoiceDetailResponse>(`/documents/${selected?.id}`), enabled: Boolean(selected?.id) })

  useEffect(() => {
    if (!selectedId && invoices.data?.items[0] && window.innerWidth >= 1180) updateParams(params, setParams, { invoice: invoices.data.items[0].id })
  }, [invoices.data, params, selectedId, setParams])

  const setFilter = (key: string, value?: string) => updateParams(params, setParams, { [key]: value || null, page: null, ...(key !== 'invoice' ? { invoice: null } : {}) })
  const summary = invoices.data?.summary

  return <div className="ops-page invoices-page">
    <PageHeader title="Invoices" description="Find, track, and inspect every invoice in one place." action={role !== 'reviewer' ? <Button variant="primary" onClick={() => setUploadOpen(true)}><Upload size={16} /> Upload invoice</Button> : null} />
    {invoices.error ? <ErrorState message={(invoices.error as Error).message} retry={() => void invoices.refetch()} /> : <>
      <div className="invoice-kpis" aria-label="Invoice summary">
        <KpiCard icon={<FileText size={22} />} label="All invoices" value={summary?.all ?? 0} />
        <KpiCard icon={<Clock3 size={22} />} label="Waiting for review" value={summary?.waiting_review ?? 0} tone="info" />
        <KpiCard icon={<AlertTriangle size={22} />} label="Needs correction" value={summary?.needs_correction ?? 0} tone="danger" />
        <KpiCard icon={<CheckCircle2 size={22} />} label="Approved" value={summary?.approved ?? 0} tone="success" />
        <KpiCard icon={<Upload size={22} />} label="Exported" value={summary?.exported ?? 0} tone="purple" />
      </div>
      <Panel className="invoice-insights" ariaLabel="Stored invoice findings"><div className="invoice-insights__title"><Sparkles size={19} /><strong>Invoice findings</strong></div><Insight value={invoices.data?.insights?.flagged ?? 0} label="Invoices flagged" /><Insight value={invoices.data?.insights?.duplicates_suspected ?? 0} label="Possible duplicates" /><Insight value={invoices.data?.insights?.tax_amount_issues ?? 0} label="Tax amount issues" /></Panel>
      <div className={`invoice-master-detail ${selected ? 'has-selection' : ''}`}>
        <Panel className="invoice-library">
          <div className="invoice-toolbar">
            <SearchField value={search} onChange={(value) => setFilter('search', value)} placeholder="Search invoices..." label="Search invoices" />
            <div className="ops-segments" aria-label="Invoice completion filter">{['all','open','completed'].map((item) => <button key={item} className={view === item ? 'is-active' : ''} onClick={() => setFilter('view', item === 'all' ? undefined : item)}>{item[0].toUpperCase()+item.slice(1)}</button>)}</div>
            <select aria-label="Status" value={status} onChange={(event) => setFilter('status', event.target.value)}><option value="">All statuses</option><option value="needs_review">Waiting for review</option><option value="needs_correction">Needs correction</option><option value="approved">Approved</option><option value="exported">Exported</option></select>
            <input className="ops-filter-input" aria-label="Vendor filter" value={vendor} onChange={(event) => setFilter('vendor', event.target.value)} placeholder="Vendor" />
            <select aria-label="Sort invoices" value={`${sort}:${direction}`} onChange={(event) => { const [nextSort,nextDirection]=event.target.value.split(':'); updateParams(params,setParams,{sort:nextSort,direction:nextDirection,page:null}) }}><option value="updated:desc">Recently updated</option><option value="invoice_date:desc">Invoice date</option><option value="amount:desc">Amount: high to low</option><option value="vendor:asc">Vendor: A-Z</option></select>
          </div>
          {invoices.isLoading ? <SkeletonRows count={8} /> : invoices.data?.items.length ? <InvoiceTable items={invoices.data.items} selectedId={selected?.id} select={(id) => setFilter('invoice', id)} /> : <EmptyState title="No invoices found" body="Try clearing the current search or filters." />}
          {invoices.data ? <Pagination page={invoices.data.page} pages={invoices.data.total_pages} total={invoices.data.total} setPage={(value) => setFilter('page', String(value))} /> : null}
        </Panel>
        {selected ? <InvoiceInspector invoice={selected} detail={detail.data} loading={detail.isLoading} error={detail.error as Error | null} reviewable={role !== 'uploader'} close={() => setFilter('invoice')} /> : null}
      </div>
    </>}
    {uploadOpen ? <UploadDialog close={() => setUploadOpen(false)} completed={() => { setUploadOpen(false); void queryClient.invalidateQueries({ queryKey: ['invoices'] }) }} /> : null}
  </div>
}

function Insight({ value, label }: { value: number; label: string }) { return <div><strong>{value}</strong><span>{label}</span></div> }

function InvoiceTable({ items, selectedId, select }: { items: InvoiceItem[]; selectedId?: string; select: (id: string) => void }) {
  return <div className="ops-table-wrap"><table className="ops-table invoice-table"><thead><tr><th aria-label="Selected" /><th>Invoice</th><th>Vendor</th><th>Invoice date</th><th>Amount</th><th>Status</th><th>Owner</th><th>Updated</th><th>Action</th></tr></thead><tbody>{items.map((invoice) => { const status = invoiceStatus(invoice.business_status); return <tr key={invoice.id} className={selectedId === invoice.id ? 'is-selected' : ''} onClick={() => select(invoice.id)}><td><span className="ops-radio" aria-hidden="true">{selectedId === invoice.id ? <i /> : null}</span></td><td><button className="ops-link" onClick={(event) => { event.stopPropagation(); select(invoice.id) }}>{invoiceLabel(invoice)}</button><small>{invoice.original_filename}</small></td><td>{invoice.vendor_name || '-'}</td><td>{formatDate(invoice.invoice_date)}</td><td>{formatMoney(invoice.total, invoice.currency)}</td><td><StatusBadge tone={status.tone}>{status.label}</StatusBadge></td><td><span className="ops-owner"><i>{initials(invoice.current_owner)}</i>{invoice.current_owner}</span></td><td>{formatDate(invoice.updated_at, true)}</td><td><button className="ops-link" onClick={(event) => { event.stopPropagation(); select(invoice.id) }}>View</button><button className="ops-icon-button" aria-label={`More actions for ${invoiceLabel(invoice)}`}><MoreVertical size={16} /></button></td></tr> })}</tbody></table></div>
}

function InvoiceInspector({ invoice, detail, loading, error, reviewable, close }: { invoice: InvoiceItem; detail?: InvoiceDetailResponse; loading: boolean; error: Error | null; reviewable: boolean; close: () => void }) {
  const status = invoiceStatus(invoice.business_status)
  const issues = detail?.extraction?.validation ?? []
  return <Panel className="invoice-inspector" ariaLabel="Invoice inspector"><header><div><span>{invoiceLabel(invoice)}</span><strong>{invoice.vendor_name || 'Vendor not detected'}</strong><b>{formatMoney(invoice.total, invoice.currency)}</b></div><button className="ops-icon-button" onClick={close} aria-label="Close invoice inspector"><X size={19} /></button></header>{error ? <ErrorState message={error.message} /> : loading ? <SkeletonRows count={5} /> : <><dl className="invoice-meta"><div><dt>Invoice date</dt><dd>{formatDate(invoice.invoice_date)}</dd></div><div><dt>Due date</dt><dd>{formatDate(invoice.due_date)}</dd></div><div><dt>Status</dt><dd><StatusBadge tone={status.tone}>{status.label}</StatusBadge></dd></div><div><dt>Owner</dt><dd>{invoice.current_owner}</dd></div><div><dt>Updated</dt><dd>{formatDate(invoice.updated_at, true)}</dd></div></dl><section className="invoice-validation"><h3>Validation findings</h3><div><span>Issues found</span><strong>{issues.length}</strong></div><div><span>Warnings</span><strong className="is-warning">{issues.filter((issue) => issue.severity !== 'error').length}</strong></div><div><span>Blockers</span><strong className="is-danger">{issues.filter((issue) => issue.severity === 'error').length}</strong></div>{issues.length===0?<p className="is-good"><CheckCircle2 size={13}/>No validation issues are stored.</p>:issues.slice(0, 2).map((issue) => <p key={issue.code}><AlertTriangle size={13} />{issue.message}</p>)}</section><div className="invoice-mini-preview"><PdfPreview url={`/documents/${invoice.id}/content`} filename={invoice.original_filename} /></div>{reviewable ? <Link className="ops-button ops-button--secondary invoice-open" to={`/review/${invoice.id}`}><FileCheck2 size={16} /> Open invoice workspace</Link> : <a className="ops-button ops-button--secondary invoice-open" href={`/documents/${invoice.id}/content`} target="_blank" rel="noreferrer"><FileCheck2 size={16} /> Open invoice PDF</a>}</> }</Panel>
}

function Pagination({ page, pages, total, setPage }: { page: number; pages: number; total: number; setPage: (page: number) => void }) {
  return <footer className="ops-pagination"><span>Showing page {page} of {pages} / {total} invoices</span><div><Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page-1)}>Previous</Button><strong>{page}</strong><Button variant="ghost" disabled={page >= pages} onClick={() => setPage(page+1)}>Next</Button></div></footer>
}

function UploadDialog({ close, completed }: { close: () => void; completed: () => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [progress, setProgress] = useState(0)
  const mutation = useMutation({ mutationFn: async () => { if (!file) throw new Error('Choose a PDF first.'); const form = new FormData(); form.append('file',file); return upload('/documents/upload',form,setProgress) }, onSuccess: completed })
  return <div className="ops-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close() }}><section className="ops-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title"><header><div><h2 id="upload-title">Upload invoice</h2><p>Add one PDF. The system will read it and place it in the correct queue.</p></div><button className="ops-icon-button" onClick={close} aria-label="Close upload"><X size={19} /></button></header><button className="invoice-dropzone" onClick={() => input.current?.click()}><Upload size={28} /><strong>{file ? file.name : 'Choose an invoice PDF'}</strong><span>{file ? `${Math.ceil(file.size/1024)} KB` : 'PDF up to the workspace upload limit'}</span></button><input ref={input} hidden type="file" accept="application/pdf,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />{mutation.isPending ? <div className="upload-progress"><span style={{ width: `${progress}%` }} /><small>{progress}% uploaded</small></div> : null}{mutation.error ? <p className="ops-form-error"><AlertTriangle size={15} />{mutation.error.message}</p> : null}<footer><Button onClick={close}>Cancel</Button><Button variant="primary" disabled={!file || mutation.isPending} onClick={() => mutation.mutate()}><Upload size={16} /> Upload invoice</Button></footer></section></div>
}

function updateParams(current: URLSearchParams, setter: ReturnType<typeof useSearchParams>[1], values: Record<string, string | null | undefined>) {
  const next = new URLSearchParams(current)
  for (const [key,value] of Object.entries(values)) {
    if (value) next.set(key,value)
    else next.delete(key)
  }
  setter(next, { replace: false })
}

function initials(value: string): string { return value.split(/\s+/).filter(Boolean).map((part) => part[0]).join('').slice(0,2).toUpperCase() || 'AI' }
