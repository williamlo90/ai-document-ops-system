import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, CheckCircle2, ChevronRight, ShieldCheck, X } from 'lucide-react'
import { api } from '../api/client'
import { PdfPreview } from '../components/PdfPreview'
import { DecisionModal } from '../features/review/components/DecisionModal'
import { DecisionPanel } from '../features/review/components/DecisionPanel'
import {
  InvoiceFieldsPanel,
  type InvoiceDraft,
} from '../features/review/components/InvoiceFieldsPanel'
import {
  canRecordDecision,
  isApprovalBlocked,
  reviewStatusText,
  reviewStatusTone,
  type DecisionKind,
} from '../features/review/selectors'
import type { InvoiceDetailResponse } from '../features/invoices/types'
import type { DecisionResult, ReviewWorkflow } from '../features/review/types'
import { formatDate, formatMoney } from '../shared/format'
import { Button, ErrorState, LoadingState, Panel, StatusBadge } from '../shared/ui'

export function ReviewWorkspacePage() {
  const { documentId = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const returnToBlocked =
    searchParams.get('state') === 'blocked' || searchParams.get('from') === 'exceptions'
  const exceptionId = searchParams.get('exception')
  const returnPath = returnToBlocked
    ? `/inbox?state=blocked${exceptionId ? `&exception=${exceptionId}` : ''}`
    : '/inbox?state=needs-decision'
  const queryClient = useQueryClient()
  const detail = useQuery({
    queryKey: ['invoice-detail', documentId],
    queryFn: () => api<InvoiceDetailResponse>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
  })
  const workflow = useQuery({
    queryKey: ['invoice-workflow', documentId],
    queryFn: () => api<ReviewWorkflow>(`/documents/${documentId}/workflow`),
    enabled: Boolean(documentId),
  })
  const [draft, setDraft] = useState<InvoiceDraft>({})
  const [savedDraft, setSavedDraft] = useState<InvoiceDraft>({})
  const [editing, setEditing] = useState<keyof InvoiceDraft | null>(null)
  const [note, setNote] = useState('')
  const [decision, setDecision] = useState<DecisionKind | null>(null)
  const [decisionPanelOpen, setDecisionPanelOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [requestedPdfPage, setRequestedPdfPage] = useState<number | null>(null)
  const [latestDecision, setLatestDecision] = useState<DecisionResult['decision'] | null>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const decisionTriggerRef = useRef<HTMLButtonElement>(null)

  const closeDecisionPanel = useCallback(() => {
    setDecisionPanelOpen(false)
    queueMicrotask(() => decisionTriggerRef.current?.focus())
  }, [])

  useEffect(() => {
    if (!detail.data?.extraction?.data) return
    setDraft(detail.data.extraction.data)
    setSavedDraft(detail.data.extraction.data)
  }, [detail.data?.document.id, detail.data?.extraction?.data])

  const dirty = JSON.stringify(draft) !== JSON.stringify(savedDraft)
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 3600)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const save = useMutation({
    mutationFn: () =>
      api(`/review/${documentId}/save`, {
        method: 'POST',
        body: JSON.stringify({ notes: note, corrected_data: draft }),
      }),
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
        if (dirty || note.trim())
          await api(`/review/${documentId}/save`, {
            method: 'POST',
            body: JSON.stringify({ notes: note, corrected_data: dirty ? draft : null }),
          })
        return api<DecisionResult>(`/review/${documentId}/approve`, { method: 'POST' })
      }
      if (kind === 'reject')
        return api<DecisionResult>(`/review/${documentId}/reject`, {
          method: 'POST',
          body: JSON.stringify({ notes: note }),
        })
      await api(`/invoices/${documentId}/request-correction`, {
        method: 'POST',
        body: JSON.stringify({ reason: note }),
      })
      return null
    },
    onSuccess: async (result, kind) => {
      setDecision(null)
      setDecisionPanelOpen(Boolean(result))
      if (result) setLatestDecision(result.decision)
      await refreshReview(queryClient, documentId)
      setToast(
        kind === 'approve'
          ? 'Invoice approved and recorded.'
          : kind === 'reject'
            ? 'Invoice rejected and recorded.'
            : 'Correction requested and recorded.',
      )
    },
  })

  if (detail.isLoading) return <LoadingState label="Loading review workspace" />
  if (detail.error)
    return (
      <ErrorState message={(detail.error as Error).message} retry={() => void detail.refetch()} />
    )
  const data = detail.data
  const document = data?.document
  const extraction = data?.extraction
  if (!document || !extraction)
    return <ErrorState message="This invoice does not have extracted data to review." />
  const blockers = extraction.validation.filter((issue) => isApprovalBlocked(issue.severity))
  const canDecide = canRecordDecision(document.status, workflow.data?.current_stage)
  const latestAudit = [...data.audit_events]
    .reverse()
    .find((event) => ['document_approved', 'document_rejected'].includes(event.event_type))

  const leave = () => {
    if (!dirty || window.confirm('Leave without saving? You have unsaved invoice changes.'))
      navigate(returnPath)
  }

  return (
    <div className="ops-page review-workspace-page">
      {toast ? (
        <div className="ops-toast" role="status">
          <CheckCircle2 size={18} />
          <span>{toast}</span>
          <button aria-label="Close message" onClick={() => setToast(null)}>
            <X size={15} />
          </button>
        </div>
      ) : null}
      <header className="review-workspace-header">
        <div>
          <nav aria-label="Breadcrumb">
            <Link to={returnPath}>Inbox</Link>
            <ChevronRight size={13} />
            <span>{draft.invoice_number || document.original_filename}</span>
          </nav>
          <div className="review-title-row">
            <h1>Review invoice</h1>
            <StatusBadge tone={reviewStatusTone(document.status)}>
              {reviewStatusText(document.status, workflow.data?.current_stage)}
            </StatusBadge>
          </div>
          <p>
            {draft.vendor_name || 'Vendor not detected'} / {formatDate(draft.invoice_date)} /{' '}
            {formatMoney(draft.total, draft.currency)}
          </p>
        </div>
        <div className="review-header-actions">
          <Button
            ref={decisionTriggerRef}
            className="review-decision-trigger"
            variant="primary"
            aria-haspopup="dialog"
            aria-expanded={decisionPanelOpen}
            onClick={() => setDecisionPanelOpen(true)}
          >
            <ShieldCheck size={17} /> {canDecide ? 'Open decision panel' : 'View decision record'}
          </Button>
          <Button onClick={leave}>
            <ArrowLeft size={16} /> Back to inbox
          </Button>
        </div>
      </header>
      <div className="review-workspace-grid">
        <Panel className="review-document-panel" ariaLabel="Invoice preview">
          <h2>Invoice preview</h2>
          <PdfPreview
            url={`/documents/${document.id}/content`}
            filename={document.original_filename}
            requestedPage={requestedPdfPage}
          />
        </Panel>
        <div className="review-side-column">
          <InvoiceFieldsPanel
            draft={draft}
            savedDraft={savedDraft}
            editing={editing}
            canDecide={canDecide}
            saving={save.isPending}
            saveError={save.error as Error | null}
            detail={data}
            setEditing={setEditing}
            setDraft={setDraft}
            save={() => save.mutate()}
            showSourcePage={setRequestedPdfPage}
          />
        </div>
      </div>
      <DecisionPanel
        open={decisionPanelOpen}
        close={closeDecisionPanel}
        canDecide={canDecide}
        blockers={blockers.length}
        note={note}
        setNote={setNote}
        select={setDecision}
        pending={submit.isPending}
        error={submit.error as Error | null}
        latestDecision={latestDecision}
        latestAudit={latestAudit}
        auditCount={data.audit_events.length}
        status={document.status}
      />
      {decision ? (
        <DecisionModal
          kind={decision}
          invoice={draft.invoice_number || document.original_filename}
          issue={blockers[0]?.message}
          note={note}
          pending={submit.isPending}
          error={submit.error as Error | null}
          cancel={() => setDecision(null)}
          confirm={() => submit.mutate(decision)}
          confirmRef={confirmRef}
        />
      ) : null}
    </div>
  )
}

async function refreshReview(queryClient: ReturnType<typeof useQueryClient>, documentId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['invoice-detail', documentId] }),
    queryClient.invalidateQueries({ queryKey: ['invoice-workflow', documentId] }),
    queryClient.invalidateQueries({ queryKey: ['review-worklist-v2'] }),
    queryClient.invalidateQueries({ queryKey: ['invoices'] }),
    queryClient.invalidateQueries({ queryKey: ['workspace'] }),
  ])
}
