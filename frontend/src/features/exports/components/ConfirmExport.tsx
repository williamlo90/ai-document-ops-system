import { CheckCircle2, FileDown, LoaderCircle, X } from 'lucide-react'
import { formatMoney } from '../../../shared/format'
import { Button } from '../../../shared/ui'
import type { ExportBatch } from '../types'

export function ConfirmExport({
  batch,
  pending,
  close,
  confirm,
}: {
  batch: ExportBatch
  pending: boolean
  close: () => void
  confirm: () => void
}) {
  return (
    <div
      className="ops-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <section
        className="ops-modal export-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-export-title"
      >
        <header>
          <div>
            <h2 id="confirm-export-title">Create export</h2>
            <p>Verify this controlled action before generating the file.</p>
          </div>
          <button className="ops-icon-button" onClick={close} aria-label="Close confirmation">
            <X size={19} />
          </button>
        </header>
        <dl>
          <div>
            <dt>Invoices</dt>
            <dd>{batch.invoice_count}</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd>
              {batch.total_amount == null
                ? 'Multiple currencies'
                : formatMoney(batch.total_amount, batch.currency)}
            </dd>
          </div>
          <div>
            <dt>Destination</dt>
            <dd>{batch.destination_label}</dd>
          </div>
          <div>
            <dt>Format</dt>
            <dd>{batch.format.toUpperCase()}</dd>
          </div>
        </dl>
        <p>
          <CheckCircle2 size={17} /> The file will be recorded only after generation succeeds.
        </p>
        <footer>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" disabled={pending} onClick={confirm}>
            {pending ? <LoaderCircle className="spin" size={16} /> : <FileDown size={16} />} Create
            export
          </Button>
        </footer>
      </section>
    </div>
  )
}
