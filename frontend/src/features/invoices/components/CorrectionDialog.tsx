import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, LoaderCircle, Send, X } from 'lucide-react'
import { api } from '../../../api/client'
import { Button } from '../../../shared/ui'
import type { InvoiceExtraction, InvoiceItem } from '../types'

const correctionFields: Array<{
  key: keyof InvoiceExtraction['data']
  label: string
  type?: string
}> = [
  { key: 'vendor_name', label: 'Vendor' },
  { key: 'invoice_number', label: 'Invoice number' },
  { key: 'invoice_date', label: 'Invoice date', type: 'date' },
  { key: 'due_date', label: 'Due date', type: 'date' },
  { key: 'subtotal', label: 'Subtotal' },
  { key: 'tax', label: 'Tax' },
  { key: 'total', label: 'Total amount' },
  { key: 'currency', label: 'Currency' },
]

export function CorrectionDialog({
  invoice,
  extraction,
  close,
  completed,
}: {
  invoice: InvoiceItem
  extraction: InvoiceExtraction
  close: () => void
  completed: () => void | Promise<void>
}) {
  const [draft, setDraft] = useState<InvoiceExtraction['data']>(() => ({
    ...extraction.data,
    line_items: extraction.data.line_items ?? [],
  }))
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () =>
      api(`/invoices/${invoice.id}/draft`, {
        method: 'POST',
        body: JSON.stringify({ ...draft, correction_reason: reason.trim() }),
      }),
    onSuccess: completed,
  })

  return (
    <div
      className="ops-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !mutation.isPending) close()
      }}
    >
      <section
        className="ops-modal invoice-correction-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="correction-title"
      >
        <header>
          <div>
            <h2 id="correction-title">Correct invoice data</h2>
            <p>
              Update only the values that differ from the PDF, then send the invoice back for
              review.
            </p>
          </div>
          <button
            className="ops-icon-button"
            disabled={mutation.isPending}
            onClick={close}
            aria-label="Close correction"
          >
            <X size={19} />
          </button>
        </header>
        {invoice.correction_reason ? (
          <div className="invoice-correction-brief">
            <AlertTriangle size={17} />
            <div>
              <strong>Reviewer note</strong>
              <p>{invoice.correction_reason}</p>
            </div>
          </div>
        ) : null}
        <div className="invoice-correction-fields">
          {correctionFields.map((field) => {
            const current = draft[field.key]
            const value = typeof current === 'string' ? current : ''
            return (
              <label key={field.key}>
                <span>{field.label}</span>
                <input
                  type={field.type ?? 'text'}
                  value={value}
                  onChange={(event) =>
                    setDraft((existing) => ({
                      ...existing,
                      [field.key]: event.target.value || null,
                    }))
                  }
                />
              </label>
            )
          })}
        </div>
        <label className="invoice-correction-reason">
          <span>What did you change?</span>
          <textarea
            maxLength={500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Example: Updated the vendor to the legal name shown on the PDF."
          />
          <small aria-hidden="true">{reason.length} / 500</small>
        </label>
        {mutation.error ? (
          <p className="ops-form-error">
            <AlertTriangle size={15} />
            {(mutation.error as Error).message}
          </p>
        ) : null}
        <footer>
          <Button disabled={mutation.isPending} onClick={close}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={mutation.isPending || reason.trim().length < 3}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />}{' '}
            {mutation.isPending ? 'Sending correction...' : 'Send to reviewer'}
          </Button>
        </footer>
      </section>
    </div>
  )
}
