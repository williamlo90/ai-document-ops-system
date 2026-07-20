import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, Check, CheckCircle2, ChevronRight, LoaderCircle, Pencil, Save, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api } from '../api/client'
import { PdfPreview } from '../components/PdfPreview'
import { formatDate, formatMoney } from '../features/invoices/format'
import type { InvoiceDetailResponse, InvoiceExtraction } from '../features/invoices/types'
import type { DecisionResult, ReviewWorkflow } from '../features/review/types'
import { Button, ErrorState, LoadingState, Panel, StatusBadge } from '../shared/ui'

type InvoiceDraft = InvoiceExtraction['data']
type DecisionKind = 'correction' | 'approve' | 'reject'

const fields: Array<{ key: keyof InvoiceDraft; label: string; type?: string }> = [
  { key: 'invoice_number', label: 'Invoice number' },
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_date', label: 'Invoice date', type: 'date' },
  { key: 'due_date', label: 'Due date', type: 'date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total amount' },
  { key: 'currency', label: 'Currency' },
]

export function ReviewWorkspacePage() {
  const { documentId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['invoice-detail', documentId], queryFn: () => api<InvoiceDetailResponse>(`/documents/${documentId}`), enabled: Boolean(documentId) })
  const workflow = useQuery({ queryKey: ['invoice-workflow', documentId], queryFn: () => api<ReviewWorkflow>(`/documents/${documentId}/workflow`), enabled: Boolean(documentId) })
  const [draft, setDraft] = useState<InvoiceDraft>({})
  const [savedDraft, setSavedDraft] = useState<InvoiceDraft>({})
  const [editing, setEditing] = useState<keyof InvoiceDraft | null>(null)
  const [note, setNote] = useState('')
  const [expandedIssue, setExpandedIssue] = useState<string | null>(null)
  const [decision, setDecision] = useState<DecisionKind | null>(null)
  const [decisionPanelOpen, setDecisionPanelOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [latestDecision, setLatestDecision] = useState<DecisionResult['decision'] | null>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!detail.data?.extraction?.data) return
    setDraft(detail.data.extraction.data)
    setSavedDraft(detail.data.extraction.data)
  }, [detail.data?.document.id, detail.data?.extraction?.data])

  const dirty = JSON.stringify(draft) !== JSON.stringify(savedDraft)
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const save = useMutation({
    mutationFn: () => api(`/review/${documentId}/save`, { method: 'POST', body: JSON.stringify({ notes: note, corrected_data: draft }) }),
    onSuccess: async () => {
      setSavedDraft(draft)
      setEditing(null)
      await refreshReview(queryClient, documentId)
      setToast('Invoice data saved and validation updated.')
    },
  })
  const submit = useMutation({
    mutationFn: async (kind: DecisionKind) => {
      if (kind === 'approve') {
        if (dirty || note.trim()) await api(`/review/${documentId}/save`, { method: 'POST', body: JSON.stringify({ notes: note, corrected_data: dirty ? draft : null }) })
        return api<DecisionResult>(`/review/${documentId}/approve`, { method: 'POST' })
      }
      if (kind === 'reject') return api<DecisionResult>(`/review/${documentId}/reject`, { method: 'POST', body: JSON.stringify({ notes: note }) })
      await api(`/invoices/${documentId}/request-correction`, { method: 'POST', body: JSON.stringify({ reason: note }) })
      return null
    },
    onSuccess: async (result, kind) => {
      setDecision(null)
      setDecisionPanelOpen(false)
      if (result) setLatestDecision(result.decision)
      await refreshReview(queryClient, documentId)
      setToast(kind === 'approve' ? 'Invoice approved and recorded.' : kind === 'reject' ? 'Invoice rejected and recorded.' : 'Correction requested and recorded.')
    },
  })

  if (detail.isLoading) return <LoadingState label="Loading review workspace" />
  if (detail.error) return <ErrorState message={(detail.error as Error).message} retry={() => void detail.refetch()} />
  const data = detail.data
  const document = data?.document
  const extraction = data?.extraction
  if (!document || !extraction) return <ErrorState message="This invoice does not have extracted data to review." />
  const issues = extraction.validation
  const blockers = issues.filter((issue) => issue.severity === 'error')
  const confidence = overallConfidence(extraction)
  const canDecide = document.status === 'needs_review' && workflow.data?.current_stage !== 'correction_requested'
  const suggested = blockers.length ? 'Request correction' : 'Approve after checking the PDF'
  const latestAudit = [...data.audit_events].reverse().find((event) => ['document_approved','document_rejected'].includes(event.event_type))

  const leave = () => {
    if (!dirty || window.confirm('Leave without saving? You have unsaved invoice changes.')) navigate('/review-queue')
  }

  return <div className="ops-page review-workspace-page">
    {toast ? <div className="ops-toast" role="status"><CheckCircle2 size={18} /><span>{toast}</span><button aria-label="Close message" onClick={() => setToast(null)}><X size={15} /></button></div> : null}
    <header className="review-workspace-header">
      <div><nav aria-label="Breadcrumb"><Link to="/review-queue">Review queue</Link><ChevronRight size={13} /><span>{draft.invoice_number || document.original_filename}</span></nav><div className="review-title-row"><h1>Review invoice</h1><StatusBadge tone={statusTone(document.status)}>{statusText(document.status, workflow.data?.current_stage)}</StatusBadge></div><p>{draft.vendor_name || 'Vendor not detected'} / {formatDate(draft.invoice_date)} / {formatMoney(draft.total,draft.currency)}</p></div>
      <Button onClick={leave}><ArrowLeft size={16} /> Back to queue</Button>
    </header>
    <Panel className="review-stepper" ariaLabel="Invoice review progress"><Step done label="Read" detail="Invoice extracted" /><Step done label="Validate" detail={issues.length ? `${issues.length} issue${issues.length === 1 ? '' : 's'} found` : 'No issues found'} /><Step done={!canDecide} active={canDecide} label="Decision" detail={canDecide ? 'Make your decision' : 'Decision recorded'} /></Panel>
    <Button className="review-decision-trigger" onClick={() => setDecisionPanelOpen(true)}><ShieldCheck size={17} /> Open decision panel</Button>
    <div className="review-workspace-grid">
      <Panel className="review-document-panel" ariaLabel="Invoice preview"><h2>Invoice preview</h2><PdfPreview url={`/documents/${document.id}/content`} filename={document.original_filename} /></Panel>
      <Panel className="review-data-panel" ariaLabel="Extracted invoice data">
        <header><h2>Extracted data</h2>{confidence == null ? <StatusBadge>Not scored</StatusBadge> : <StatusBadge tone="success">{Math.round(confidence*100)}% confidence</StatusBadge>}</header>
        <div className="review-edit-fields">{fields.map((field) => <EditableField key={field.key} field={field} value={draft[field.key]} editing={editing === field.key} disabled={!canDecide || save.isPending} onEdit={() => setEditing(field.key)} onCancel={() => { setDraft((current) => ({ ...current, [field.key]: savedDraft[field.key] })); setEditing(null) }} onChange={(value) => setDraft((current) => ({ ...current, [field.key]: value }))} onSave={() => save.mutate()} />)}</div>
        {save.error ? <p className="review-inline-error"><AlertCircle size={14} />{(save.error as Error).message}</p> : null}
        <section className="review-evidence"><h3>Evidence & checks <StatusBadge tone={blockers.length ? 'danger' : 'success'}>{blockers.length ? `${blockers.length} blocker${blockers.length === 1 ? '' : 's'}` : 'Passed'}</StatusBadge></h3>{issues.length ? issues.map((issue) => <button key={issue.code} className="review-evidence-row" onClick={() => setExpandedIssue(expandedIssue === issue.code ? null : issue.code)}><span><AlertCircle size={15} />{issue.message}</span><StatusBadge tone={issue.severity === 'error' ? 'danger' : 'warning'}>{issue.severity === 'error' ? 'Blocker' : 'Check'}</StatusBadge>{expandedIssue === issue.code ? <small>Observed field: {issue.field_name || 'invoice'} / Rule: {issue.code}. This stored validation result determines whether approval is allowed.</small> : null}</button>) : <p className="review-check-clear"><Check size={15} /> No validation blockers were found.</p>}</section>
        <LineItems items={draft.line_items ?? []} currency={draft.currency} total={draft.total} />
      </Panel>
      <DecisionPanel open={decisionPanelOpen} close={() => setDecisionPanelOpen(false)} canDecide={canDecide} blockers={blockers.length} confidence={confidence} suggested={suggested} note={note} setNote={setNote} select={setDecision} pending={submit.isPending} error={submit.error as Error | null} latestDecision={latestDecision} latestAudit={latestAudit} auditCount={data.audit_events.length} status={document.status} />
    </div>
    {decision ? <DecisionModal kind={decision} invoice={draft.invoice_number || document.original_filename} issue={blockers[0]?.message} note={note} pending={submit.isPending} error={submit.error as Error | null} cancel={() => setDecision(null)} confirm={() => submit.mutate(decision)} confirmRef={confirmRef} /> : null}
  </div>
}

function Step({ done, active, label, detail }: { done?: boolean; active?: boolean; label: string; detail: string }) { return <div className={active ? 'is-active' : done ? 'is-done' : ''}><span>{done ? <Check size={16} /> : label === 'Decision' ? '3' : '2'}</span><p><strong>{label}</strong><small>{detail}</small></p></div> }

function EditableField({ field, value, editing, disabled, onEdit, onCancel, onChange, onSave }: { field: (typeof fields)[number]; value: unknown; editing: boolean; disabled: boolean; onEdit: () => void; onCancel: () => void; onChange: (value: string) => void; onSave: () => void }) {
  const text = typeof value === 'string' ? value : ''
  return <div className={!text ? 'is-missing' : ''}><span>{field.label}</span>{editing ? <div className="review-field-editor"><input autoFocus type={field.type || 'text'} value={text} onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') onSave(); if (event.key === 'Escape') onCancel() }} /><button aria-label={`Save ${field.label}`} onClick={onSave}><Save size={14} /></button><button aria-label={`Cancel ${field.label}`} onClick={onCancel}><X size={14} /></button></div> : <><strong>{text || 'Missing'}</strong><button aria-label={`Edit ${field.label}`} disabled={disabled} onClick={onEdit}><Pencil size={14} /></button></>}</div>
}

function LineItems({ items, currency, total }: { items: Array<Record<string,string|null>>; currency?: string | null; total?: string | null }) { return <section className="review-line-items"><h3>Line items <span>{items.length} items</span></h3>{items.length ? <div className="ops-table-wrap"><table><thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>{items.map((item,index)=><tr key={`${item.description}-${index}`}><td>{item.description||'-'}</td><td>{item.quantity||'-'}</td><td>{formatMoney(item.unit_price,currency)}</td><td>{formatMoney(item.amount,currency)}</td></tr>)}</tbody><tfoot><tr><td colSpan={3}>Total</td><td>{formatMoney(total,currency)}</td></tr></tfoot></table></div> : <p>No line items were extracted.</p>}</section> }

function DecisionPanel({ open, close, canDecide, blockers, confidence, suggested, note, setNote, select, pending, error, latestDecision, latestAudit, auditCount, status }: { open:boolean; close:()=>void; canDecide:boolean; blockers:number; confidence:number|null; suggested:string; note:string; setNote:(value:string)=>void; select:(kind:DecisionKind)=>void; pending:boolean; error:Error|null; latestDecision:DecisionResult['decision']|null; latestAudit:InvoiceDetailResponse['audit_events'][number]|undefined; auditCount:number; status:string }) {
  return <Panel className={`review-decision-panel ${open ? 'is-open' : ''}`} ariaLabel="Reviewer decision"><header><h2>Decision</h2><button className="ops-icon-button review-decision-close" aria-label="Close decision panel" onClick={close}><X size={18}/></button></header>{canDecide ? <><section className={blockers ? 'review-recommendation-card is-blocked' : 'review-recommendation-card'}><header><Sparkles size={17}/><strong>Review recommendation</strong>{confidence == null ? null : <StatusBadge tone="success">{Math.round(confidence*100)}% extraction confidence</StatusBadge>}</header><span>Recommended action</span><h3>{suggested}</h3><p>{blockers ? `${blockers} validation blocker${blockers===1?' remains':'s remain'}. The reviewer must request a correction or reject this invoice.` : 'No blocking validation issue is stored. Compare the fields with the PDF before approving.'}</p><small>This recommendation assists the reviewer and does not make the final decision.</small></section><label className="review-note"><span>Decision note {blockers ? <b>*</b> : '(optional for approval)'}</span><textarea maxLength={1000} value={note} onChange={(event)=>setNote(event.target.value)} placeholder="Explain the decision for the audit trail..."/><small>{note.length} / 1000</small></label><div className="review-decision-actions"><Button variant="danger" disabled={pending||note.trim().length<3} onClick={()=>select('correction')}><AlertCircle size={16}/> Request correction</Button><Button disabled={pending||blockers>0} title={blockers?'Resolve validation blockers before approval':undefined} onClick={()=>select('approve')}><CheckCircle2 size={16}/> Approve</Button><Button disabled={pending||note.trim().length<3} onClick={()=>select('reject')}><X size={16}/> Reject</Button></div>{error?<p className="review-inline-error"><AlertCircle size={14}/>{error.message}</p>:null}</> : <DecisionEvidence decision={latestDecision} latestAudit={latestAudit} auditCount={auditCount} status={status} />}</Panel>
}

function DecisionEvidence({ decision, latestAudit, auditCount, status }: { decision:DecisionResult['decision']|null; latestAudit:InvoiceDetailResponse['audit_events'][number]|undefined; auditCount:number; status:string }) { const actor=decision?.actor||latestAudit?.actor||'Recorded reviewer'; const time=decision?.recorded_at||latestAudit?.created_at; return <section className="review-recorded"><CheckCircle2 size={30}/><h3>Decision recorded</h3><p>This invoice is {status.replaceAll('_',' ')}. The recorded outcome cannot be submitted again.</p><dl><div><dt>Recorded by</dt><dd>{actor}</dd></div><div><dt>Recorded at</dt><dd>{time?new Date(time).toLocaleString():'Not available'}</dd></div><div><dt>Audit trail</dt><dd>{decision?.audit_event_count??auditCount} events</dd></div><div><dt>Export</dt><dd>{decision?.export_eligibility==='eligible'||status==='approved'?'Eligible after approval':'Not eligible'}</dd></div></dl></section> }

function DecisionModal({ kind, invoice, issue, note, pending, error, cancel, confirm, confirmRef }: { kind:DecisionKind; invoice:string; issue?:string; note:string; pending:boolean; error:Error|null; cancel:()=>void; confirm:()=>void; confirmRef:React.RefObject<HTMLButtonElement|null> }) { const title=kind==='approve'?'Approve invoice?':kind==='reject'?'Reject invoice?':'Request correction?'; useEffect(()=>{confirmRef.current?.focus(); const close=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!pending)cancel()}; window.addEventListener('keydown',close); return()=>window.removeEventListener('keydown',close)},[cancel,confirmRef,pending]); return <div className="ops-modal-backdrop" role="presentation" onMouseDown={(event)=>{if(event.target===event.currentTarget&&!pending)cancel()}}><section className="ops-modal review-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="decision-confirm-title"><header><div><h2 id="decision-confirm-title">{title}</h2><p>This action will be recorded in the audit trail.</p></div></header><dl><div><dt>Invoice</dt><dd>{invoice}</dd></div>{issue?<div><dt>Issue</dt><dd>{issue}</dd></div>:null}{note?<div><dt>Decision note</dt><dd>{note}</dd></div>:null}</dl>{error?<p className="review-inline-error"><AlertCircle size={14}/>{error.message} Your note has been preserved.</p>:null}<footer><Button disabled={pending} onClick={cancel}>Cancel</Button><Button ref={confirmRef} variant={kind==='approve'?'primary':'danger'} disabled={pending} onClick={confirm}>{pending?<LoaderCircle className="spin" size={16}/>:kind==='approve'?<Check size={16}/>:<AlertCircle size={16}/>} {pending?'Saving decision...':kind==='approve'?'Approve':kind==='reject'?'Reject':'Request correction'}</Button></footer></section></div> }

function overallConfidence(extraction:InvoiceExtraction):number|null { const values=extraction.confidence.map((item)=>item.score).filter((score)=>score!=null).map(Number).filter((score)=>Number.isFinite(score)); return values.length?values.reduce((sum,value)=>sum+value,0)/values.length:null }
function statusTone(status:string):'success'|'danger'|'warning'|'info' { return status==='approved'?'success':status==='rejected'?'danger':status==='needs_review'?'warning':'info' }
function statusText(status:string, stage?:string):string { if(['approved','rejected','exported'].includes(status))return status.replace(/\b\w/g,(value)=>value.toUpperCase()); if(stage==='correction_requested')return 'Correction requested'; return status.replaceAll('_',' ').replace(/\b\w/g,(value)=>value.toUpperCase()) }
async function refreshReview(queryClient:ReturnType<typeof useQueryClient>,documentId:string){ await Promise.all([queryClient.invalidateQueries({queryKey:['invoice-detail',documentId]}),queryClient.invalidateQueries({queryKey:['invoice-workflow',documentId]}),queryClient.invalidateQueries({queryKey:['review-worklist-v2']}),queryClient.invalidateQueries({queryKey:['invoices']}),queryClient.invalidateQueries({queryKey:['workspace']})]) }
