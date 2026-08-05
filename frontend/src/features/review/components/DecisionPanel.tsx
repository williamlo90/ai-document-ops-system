import { useEffect, useRef } from 'react'
import { AlertCircle, CheckCircle2, ShieldCheck, X } from 'lucide-react'
import type { InvoiceDetailResponse } from '../../invoices/types'
import { Button } from '../../../shared/ui'
import type { DecisionResult } from '../types'
import type { DecisionKind } from '../selectors'

export type DecisionPanelProps = {
  open: boolean
  close: () => void
  canDecide: boolean
  blockers: number
  note: string
  setNote: (value: string) => void
  select: (kind: DecisionKind) => void
  pending: boolean
  error: Error | null
  latestDecision: DecisionResult['decision'] | null
  latestAudit: InvoiceDetailResponse['audit_events'][number] | undefined
  auditCount: number
  status: string
}

export function DecisionPanel({
  open,
  close,
  canDecide,
  blockers,
  note,
  setNote,
  select,
  pending,
  error,
  latestDecision,
  latestAudit,
  auditCount,
  status,
}: DecisionPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        close()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href]',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [close, open])

  if (!open) return null

  return (
    <div
      className="review-decision-backdrop"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        ref={panelRef}
        className="ops-panel review-decision-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-decision-title"
      >
        <header>
          <h2 id="review-decision-title">Reviewer decision</h2>
          <button
            ref={closeRef}
            className="ops-icon-button review-decision-close"
            aria-label="Close decision panel"
            onClick={close}
          >
            <X size={18} />
          </button>
        </header>
        {canDecide ? (
          <>
            <div className="review-decision-content">
              <section
                className={
                  blockers ? 'review-recommendation-card is-blocked' : 'review-recommendation-card'
                }
              >
                <header>
                  <ShieldCheck size={17} />
                  <strong>{blockers ? 'Approval blocked' : 'Ready for a decision'}</strong>
                </header>
                <h3>
                  {blockers
                    ? `${blockers} validation blocker${blockers === 1 ? '' : 's'}`
                    : 'No validation blockers'}
                </h3>
                <p>
                  {blockers
                    ? 'Request a correction or reject this invoice. Approval remains unavailable until validation passes.'
                    : 'Compare the invoice data with the PDF before approving.'}
                </p>
              </section>
              <label className="review-note">
                <span>Decision note {blockers ? <b>*</b> : '(optional for approval)'}</span>
                <textarea
                  maxLength={1000}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Explain the decision for the audit trail..."
                />
                <small>{note.length} / 1000</small>
              </label>
              {error ? (
                <p className="review-inline-error">
                  <AlertCircle size={14} />
                  {error.message}
                </p>
              ) : null}
            </div>
            <footer className="review-decision-actions">
              <Button
                variant="primary"
                disabled={pending || note.trim().length < 3}
                onClick={() => select('correction')}
              >
                <AlertCircle size={16} /> Request correction
              </Button>
              <Button
                disabled={pending || blockers > 0}
                title={blockers ? 'Resolve validation blockers before approval' : undefined}
                onClick={() => select('approve')}
              >
                <CheckCircle2 size={16} /> Approve
              </Button>
              <Button
                variant="danger"
                disabled={pending || note.trim().length < 3}
                onClick={() => select('reject')}
              >
                <X size={16} /> Reject
              </Button>
            </footer>
          </>
        ) : (
          <div className="review-decision-content">
            <DecisionEvidence
              decision={latestDecision}
              latestAudit={latestAudit}
              auditCount={auditCount}
              status={status}
            />
          </div>
        )}
      </aside>
    </div>
  )
}

function DecisionEvidence({
  decision,
  latestAudit,
  auditCount,
  status,
}: {
  decision: DecisionResult['decision'] | null
  latestAudit: InvoiceDetailResponse['audit_events'][number] | undefined
  auditCount: number
  status: string
}) {
  const actor = decision?.actor || latestAudit?.actor || 'Recorded reviewer'
  const time = decision?.recorded_at || latestAudit?.created_at
  return (
    <section className="review-recorded">
      <CheckCircle2 size={30} />
      <h3>Decision recorded</h3>
      <p>
        This invoice is {status.replaceAll('_', ' ')}. The recorded outcome cannot be submitted
        again.
      </p>
      <dl>
        <div>
          <dt>Recorded by</dt>
          <dd>{actor}</dd>
        </div>
        <div>
          <dt>Recorded at</dt>
          <dd>{time ? new Date(time).toLocaleString() : 'Not available'}</dd>
        </div>
        <div>
          <dt>Audit trail</dt>
          <dd>{decision?.audit_event_count ?? auditCount} events</dd>
        </div>
        <div>
          <dt>Export</dt>
          <dd>
            {decision?.export_eligibility === 'eligible' || status === 'approved'
              ? 'Eligible after approval'
              : 'Not eligible'}
          </dd>
        </div>
      </dl>
    </section>
  )
}
