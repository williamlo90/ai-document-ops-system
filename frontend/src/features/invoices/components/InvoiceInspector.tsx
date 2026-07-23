import { useEffect, useRef } from 'react'
import { AlertTriangle, CheckCircle2, FileCheck2, Send, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate, formatMoney, invoiceLabel } from '../format'
import { invoiceStatus } from '../selectors'
import type { InvoiceDetailResponse, InvoiceItem } from '../types'
import { Button, ErrorState, SkeletonRows, StatusBadge } from '../../../shared/ui'

export function InvoiceInspector({
  invoice,
  detail,
  loading,
  error,
  reviewable,
  correctable,
  correct,
  close,
}: {
  invoice: InvoiceItem
  detail?: InvoiceDetailResponse
  loading: boolean
  error: Error | null
  reviewable: boolean
  correctable: boolean
  correct: () => void
  close: () => void
}) {
  const status = invoiceStatus(invoice.business_status)
  const issues = detail?.extraction?.validation ?? []
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
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
        'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled])',
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
  }, [close])

  return (
    <div
      className="invoice-inspector-backdrop"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        ref={panelRef}
        className="ops-panel invoice-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="invoice-inspector-title"
      >
        <header>
          <div>
            <span id="invoice-inspector-title">{invoiceLabel(invoice)}</span>
            <strong>{invoice.vendor_name || 'Vendor not detected'}</strong>
            <b>{formatMoney(invoice.total, invoice.currency)}</b>
          </div>
          <button
            ref={closeRef}
            className="ops-icon-button"
            onClick={close}
            aria-label="Close invoice inspector"
          >
            <X size={19} />
          </button>
        </header>
        <div className="invoice-inspector-content">
          {error ? (
            <ErrorState message={error.message} />
          ) : loading ? (
            <SkeletonRows count={5} />
          ) : (
            <>
              <dl className="invoice-meta">
                <div>
                  <dt>Invoice date</dt>
                  <dd>{formatDate(invoice.invoice_date)}</dd>
                </div>
                <div>
                  <dt>Due date</dt>
                  <dd>{formatDate(invoice.due_date)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                  </dd>
                </div>
                <div>
                  <dt>Owner</dt>
                  <dd>{invoice.current_owner}</dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>{formatDate(invoice.updated_at, true)}</dd>
                </div>
              </dl>
              {invoice.correction_reason ? (
                <section className="invoice-correction-request">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Reviewer requested a correction</strong>
                    <p>{invoice.correction_reason}</p>
                  </div>
                </section>
              ) : null}
              <section className="invoice-validation">
                <h3>Validation findings</h3>
                <div>
                  <span>Issues found</span>
                  <strong>{issues.length}</strong>
                </div>
                <div>
                  <span>Warnings</span>
                  <strong className="is-warning">
                    {issues.filter((issue) => issue.severity !== 'error').length}
                  </strong>
                </div>
                <div>
                  <span>Blockers</span>
                  <strong className="is-danger">
                    {issues.filter((issue) => issue.severity === 'error').length}
                  </strong>
                </div>
                {issues.length === 0 ? (
                  <p className="is-good">
                    <CheckCircle2 size={13} />
                    No validation issues are stored.
                  </p>
                ) : (
                  issues.slice(0, 2).map((issue) => (
                    <p key={issue.code}>
                      <AlertTriangle size={13} />
                      {issue.message}
                    </p>
                  ))
                )}
              </section>
              <a
                className="invoice-document-link"
                href={`/documents/${invoice.id}/content`}
                target="_blank"
                rel="noreferrer"
              >
                <FileCheck2 size={19} />
                <span>
                  <strong>Invoice PDF</strong>
                  <small>{invoice.original_filename}</small>
                </span>
                <b>Open PDF</b>
              </a>
            </>
          )}
        </div>
        {!error && !loading ? (
          <footer className="invoice-inspector-actions">
            {correctable ? (
              <Button variant="primary" onClick={correct}>
                <Send size={16} /> Correct invoice data
              </Button>
            ) : null}
            {reviewable ? (
              <Link className="ops-button ops-button--secondary" to={`/review/${invoice.id}`}>
                <FileCheck2 size={16} /> Open invoice workspace
              </Link>
            ) : null}
          </footer>
        ) : null}
      </aside>
    </div>
  )
}
