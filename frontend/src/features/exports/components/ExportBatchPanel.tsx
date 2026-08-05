import { useEffect, useRef } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Download,
  ListChecks,
  Play,
  Save,
  X,
} from 'lucide-react'
import { formatDate, formatMoney } from '../../../shared/format'
import { Button, EmptyState, SkeletonRows, StatusBadge } from '../../../shared/ui'
import type { ExportBatch, ExportInvoiceItem, ExportRun } from '../types'

export type ExportBatchPanelProps = {
  batch: ExportBatch | null
  selectedItems: ExportInvoiceItem[]
  selectedAmount: number
  selectedCurrency: string | null
  open: boolean
  loading: boolean
  mutationError: Error | null
  expanded: boolean
  setExpanded: (value: boolean) => void
  close: () => void
  saveDraft: () => void
  execute: () => void
  canExecute: boolean
  recentRuns: ExportRun[]
  openRun: (id: string) => void
}

export function ExportBatchPanel({
  batch,
  selectedItems,
  selectedAmount,
  selectedCurrency,
  open,
  loading,
  mutationError,
  expanded,
  setExpanded,
  close,
  saveDraft,
  execute,
  canExecute,
  recentRuns,
  openRun,
}: ExportBatchPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const invoices = batch?.invoices ?? selectedItems
  const count = batch?.invoice_count ?? selectedItems.length
  const amount = batch ? batch.total_amount : selectedCurrency ? String(selectedAmount) : null
  const currency = batch?.currency ?? selectedCurrency
  const completedRun = batch?.last_run_id
    ? recentRuns.find((run) => run.id === batch.last_run_id)
    : undefined

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
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled])',
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
      className="export-batch-backdrop"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        ref={panelRef}
        className="export-batch-panel is-open"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-batch-title"
      >
        <header>
          <h2 id="export-batch-title">Export batch</h2>
          <button
            ref={closeRef}
            className="ops-icon-button export-batch-close"
            aria-label="Close export batch"
            onClick={close}
          >
            <X size={19} />
          </button>
        </header>
        <div className="export-batch-content">
          {loading ? (
            <SkeletonRows count={6} />
          ) : count ? (
            <>
              <section className="export-batch-summary">
                <div>
                  <strong>
                    {count} {count === 1 ? 'invoice' : 'invoices'}{' '}
                    {batch?.status === 'completed' ? 'exported' : batch ? 'in batch' : 'selected'}
                  </strong>
                  {!batch ? (
                    <button className="ops-link" onClick={close}>
                      Change selection
                    </button>
                  ) : null}
                </div>
                <span>Total amount</span>
                <b>{amount == null ? 'Multiple currencies' : formatMoney(amount, currency)}</b>
                <button className="ops-link" onClick={() => setExpanded(!expanded)}>
                  View invoices <ChevronDown size={14} className={expanded ? 'is-rotated' : ''} />
                </button>
                {expanded ? (
                  <ul>
                    {invoices.map((item) => (
                      <li key={item.id}>
                        <span>{item.invoice_label}</span>
                        <strong>{formatMoney(item.total, item.currency)}</strong>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>
              <dl className="export-configuration">
                <div>
                  <dt>Destination</dt>
                  <dd>{batch?.destination_label ?? 'CSV download'}</dd>
                </div>
                <div>
                  <dt>Export format</dt>
                  <dd>{(batch?.format ?? 'csv').toUpperCase()}</dd>
                </div>
                <div>
                  <dt>File name</dt>
                  <dd>{completedRun?.file_name ?? 'Generated securely at export'}</dd>
                </div>
              </dl>
              {batch?.status === 'completed' ? (
                <section className="export-checks export-completion">
                  <h3>Export completed</h3>
                  <div className="is-passed">
                    <CheckCircle2 size={16} />
                    <span>File generated and run recorded</span>
                  </div>
                  <p>Invoice status changed only after the export file was created successfully.</p>
                </section>
              ) : (
                <section className="export-checks">
                  <h3>Eligibility checks</h3>
                  {batch ? (
                    batch.eligibility.map((check) => (
                      <div
                        key={check.code}
                        title={check.detail}
                        className={check.state === 'passed' ? 'is-passed' : 'is-failed'}
                      >
                        {check.state === 'passed' ? (
                          <CheckCircle2 size={16} />
                        ) : (
                          <AlertCircle size={16} />
                        )}
                        <span>{check.label}</span>
                      </div>
                    ))
                  ) : (
                    <div className="is-pending">
                      <ListChecks size={16} />
                      <span>Server checks run when invoices are added</span>
                    </div>
                  )}
                </section>
              )}
              {mutationError ? (
                <p className="export-panel-error">
                  <AlertTriangle size={16} />
                  {mutationError.message}
                </p>
              ) : null}
              <div className="export-panel-actions">
                {batch?.status === 'completed' && batch.last_run_id ? (
                  <a
                    className="ops-button ops-button--primary"
                    href={`/exports/runs/${batch.last_run_id}/download`}
                  >
                    <Download size={16} /> Download export
                  </a>
                ) : batch ? (
                  <Button variant="primary" disabled={!canExecute} onClick={execute}>
                    <Play size={16} /> Create export
                  </Button>
                ) : null}
                {batch?.status !== 'completed' ? (
                  <Button onClick={saveDraft}>
                    <Save size={16} /> Save selection as draft
                  </Button>
                ) : null}
                {!canExecute && batch?.status === 'ready' ? (
                  <small>Resolve the failed eligibility check before exporting.</small>
                ) : null}
              </div>
            </>
          ) : (
            <EmptyState
              title="No export batch yet"
              body="Select approved invoices from the Ready tab to prepare an export."
            />
          )}
          <section className="export-recent-runs">
            <header>
              <h3>Recent export runs</h3>
            </header>
            {recentRuns.length ? (
              recentRuns.map((run) => (
                <button key={run.id} onClick={() => openRun(run.id)}>
                  <span>
                    <b>{run.file_name || `Run ${run.id.slice(0, 8)}`}</b>
                    <small>{formatDate(run.created_at, true)}</small>
                  </span>
                  <StatusBadge
                    tone={
                      run.status === 'succeeded'
                        ? 'success'
                        : run.status === 'failed'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {run.status}
                  </StatusBadge>
                </button>
              ))
            ) : (
              <p>No exports have been run yet.</p>
            )}
          </section>
        </div>
      </aside>
    </div>
  )
}
