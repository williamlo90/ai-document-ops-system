import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle, Check, Clock3, Download, RotateCcw, X } from 'lucide-react'
import { api } from '../../../api/client'
import { formatDate, formatMoney } from '../../../shared/format'
import { Button, ErrorState, SkeletonRows, StatusBadge } from '../../../shared/ui'
import type { ExportRun } from '../types'

export function RunDrawer({
  runId,
  close,
  refresh,
}: {
  runId: string
  close: () => void
  refresh: () => void
}) {
  const run = useQuery({
    queryKey: ['export-run', runId],
    queryFn: () => api<{ run: ExportRun }>(`/exports/runs/${runId}`),
  })
  const retry = useMutation({
    mutationFn: () =>
      api<{ run: ExportRun }>(`/exports/runs/${runId}/retry`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      }),
    onSuccess: () => {
      void run.refetch()
      refresh()
    },
  })
  return (
    <div
      className="ops-modal-backdrop export-run-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        className="export-run-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-run-title"
      >
        <header>
          <div>
            <span>Export run</span>
            <h2 id="export-run-title">{run.data?.run.file_name || runId.slice(0, 8)}</h2>
          </div>
          <button className="ops-icon-button" onClick={close} aria-label="Close export run">
            <X size={19} />
          </button>
        </header>
        {run.error ? (
          <ErrorState message={(run.error as Error).message} retry={() => void run.refetch()} />
        ) : run.isLoading ? (
          <SkeletonRows count={7} />
        ) : run.data ? (
          <>
            <div className="export-run-verdict">
              <StatusBadge
                tone={
                  run.data.run.status === 'succeeded'
                    ? 'success'
                    : run.data.run.status === 'failed'
                      ? 'danger'
                      : 'warning'
                }
              >
                {run.data.run.status}
              </StatusBadge>
              <strong>{run.data.run.invoice_count} invoices</strong>
              <span>
                {run.data.run.total_amount == null
                  ? 'Multiple currencies'
                  : formatMoney(run.data.run.total_amount, run.data.run.currency)}
              </span>
            </div>
            <dl>
              <div>
                <dt>Destination</dt>
                <dd>{run.data.run.destination_label}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{formatDate(run.data.run.created_at, true)}</dd>
              </div>
              <div>
                <dt>Completed</dt>
                <dd>{formatDate(run.data.run.completed_at, true)}</dd>
              </div>
              <div>
                <dt>Operator</dt>
                <dd>{run.data.run.actor}</dd>
              </div>
              <div>
                <dt>Attempts</dt>
                <dd>{run.data.run.attempt_count}</dd>
              </div>
            </dl>
            <section>
              <h3>Execution stages</h3>
              {run.data.run.stages?.map((stage) => (
                <div key={stage.label} className={`export-run-stage is-${stage.status}`}>
                  {stage.status === 'completed' ? (
                    <Check size={15} />
                  ) : stage.status === 'failed' ? (
                    <AlertCircle size={15} />
                  ) : (
                    <Clock3 size={15} />
                  )}
                  <span>{stage.label}</span>
                  <b>{stage.status.replace('_', ' ')}</b>
                </div>
              ))}
            </section>
            {run.data.run.error_message ? (
              <p className="export-panel-error">
                <AlertTriangle size={16} />
                {run.data.run.error_message} No invoice was marked exported by this failed run.
              </p>
            ) : null}
            <footer>
              {run.data.run.download_available ? (
                <a
                  className="ops-button ops-button--primary"
                  href={`/exports/runs/${runId}/download`}
                >
                  <Download size={16} /> Download file
                </a>
              ) : null}
              {run.data.run.retryable ? (
                <Button disabled={retry.isPending} onClick={() => retry.mutate()}>
                  <RotateCcw size={16} /> Retry export
                </Button>
              ) : null}
            </footer>
          </>
        ) : null}
      </aside>
    </div>
  )
}
