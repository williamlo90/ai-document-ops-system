import { AlertCircle, Check, CheckCircle2, Pencil, Save, X } from 'lucide-react'
import { formatMoney } from '../../../shared/format'
import type { InvoiceDetailResponse, InvoiceExtraction } from '../../invoices/types'
import { Panel, StatusBadge } from '../../../shared/ui'

export type InvoiceDraft = InvoiceExtraction['data']

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

export type InvoiceFieldsPanelProps = {
  draft: InvoiceDraft
  savedDraft: InvoiceDraft
  editing: keyof InvoiceDraft | null
  canDecide: boolean
  saving: boolean
  saveError: Error | null
  detail: InvoiceDetailResponse
  setEditing: (field: keyof InvoiceDraft | null) => void
  setDraft: React.Dispatch<React.SetStateAction<InvoiceDraft>>
  save: () => void
}

export function InvoiceFieldsPanel({
  draft,
  savedDraft,
  editing,
  canDecide,
  saving,
  saveError,
  detail,
  setEditing,
  setDraft,
  save,
}: InvoiceFieldsPanelProps) {
  const issues = detail.extraction?.validation ?? []
  const blockers = issues.filter((issue) => issue.severity === 'error')

  return (
    <Panel className="review-data-panel" ariaLabel="Extracted invoice data">
      <header>
        <h2>Invoice data</h2>
      </header>
      <section className={`review-inline-decision-summary ${blockers.length ? 'is-blocked' : ''}`}>
        {blockers.length ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
        <div>
          <strong>{blockers.length ? 'Approval blocked' : 'Ready for decision'}</strong>
          <span>
            {blockers.length
              ? blockers[0].message
              : 'No validation blockers. Compare the values with the PDF before deciding.'}
          </span>
        </div>
      </section>
      {detail.correction_summary ? (
        <section className="review-correction-summary">
          <CheckCircle2 size={17} />
          <div>
            <strong>
              {detail.correction_summary.latest_change_count} field
              {detail.correction_summary.latest_change_count === 1 ? '' : 's'} corrected by{' '}
              {detail.correction_summary.latest_actor}
            </strong>
            <p>
              {detail.correction_summary.latest_changed_fields
                .map((field) => field.replaceAll('_', ' '))
                .join(', ')}
              . {detail.correction_summary.latest_reason}
            </p>
          </div>
        </section>
      ) : null}
      <div className="review-edit-fields">
        {fields.map((field) => (
          <EditableField
            key={field.key}
            field={field}
            value={draft[field.key]}
            editing={editing === field.key}
            disabled={!canDecide || saving}
            onEdit={() => setEditing(field.key)}
            onCancel={() => {
              setDraft((current) => ({ ...current, [field.key]: savedDraft[field.key] }))
              setEditing(null)
            }}
            onChange={(value) => setDraft((current) => ({ ...current, [field.key]: value }))}
            onSave={save}
          />
        ))}
      </div>
      {saveError ? (
        <p className="review-inline-error">
          <AlertCircle size={14} />
          {saveError.message}
        </p>
      ) : null}
      <section className="review-evidence">
        <h3>
          Validation checks{' '}
          <StatusBadge tone={blockers.length ? 'danger' : 'success'}>
            {blockers.length
              ? `${blockers.length} blocker${blockers.length === 1 ? '' : 's'}`
              : 'Passed'}
          </StatusBadge>
        </h3>
        {issues.length ? (
          issues.map((issue) => (
            <div key={issue.code} className="review-evidence-row">
              <span>
                <AlertCircle size={15} />
                {issue.message}
              </span>
              <StatusBadge tone={issue.severity === 'error' ? 'danger' : 'warning'}>
                {issue.severity === 'error' ? 'Blocker' : 'Check'}
              </StatusBadge>
            </div>
          ))
        ) : (
          <p className="review-check-clear">
            <Check size={15} /> No validation blockers were found.
          </p>
        )}
      </section>
      <LineItems items={draft.line_items ?? []} currency={draft.currency} total={draft.total} />
    </Panel>
  )
}

function EditableField({
  field,
  value,
  editing,
  disabled,
  onEdit,
  onCancel,
  onChange,
  onSave,
}: {
  field: (typeof fields)[number]
  value: unknown
  editing: boolean
  disabled: boolean
  onEdit: () => void
  onCancel: () => void
  onChange: (value: string) => void
  onSave: () => void
}) {
  const text = typeof value === 'string' ? value : ''
  return (
    <div className={!text ? 'is-missing' : ''}>
      <span>{field.label}</span>
      {editing ? (
        <div className="review-field-editor">
          <input
            autoFocus
            type={field.type || 'text'}
            value={text}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSave()
              if (event.key === 'Escape') onCancel()
            }}
          />
          <button aria-label={`Save ${field.label}`} onClick={onSave}>
            <Save size={14} />
          </button>
          <button aria-label={`Cancel ${field.label}`} onClick={onCancel}>
            <X size={14} />
          </button>
        </div>
      ) : (
        <>
          <strong>{text || 'Missing'}</strong>
          <button aria-label={`Edit ${field.label}`} disabled={disabled} onClick={onEdit}>
            <Pencil size={14} />
          </button>
        </>
      )}
    </div>
  )
}

function LineItems({
  items,
  currency,
  total,
}: {
  items: Array<Record<string, string | null>>
  currency?: string | null
  total?: string | null
}) {
  return (
    <section className="review-line-items">
      <h3>
        Line items <span>{items.length} items</span>
      </h3>
      {items.length ? (
        <div className="ops-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Description</th>
                <th>Qty</th>
                <th>Rate</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={`${item.description}-${index}`}>
                  <td>{item.description || '-'}</td>
                  <td>{item.quantity || '-'}</td>
                  <td>{formatMoney(item.unit_price, currency)}</td>
                  <td>{formatMoney(item.amount, currency)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>Total</td>
                <td>{formatMoney(total, currency)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <p>No line items were extracted.</p>
      )}
    </section>
  )
}
