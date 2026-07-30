import { ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import { formatDate, formatMoney } from '../../../shared/format'
import { StatusBadge } from '../../../shared/ui'
import type { ExportInvoiceItem } from '../types'
import { isExportReady } from '../selectors'

export function ExportTable({
  items,
  selectable,
  selectedIds,
  allSelected,
  toggle,
  toggleAll,
  openBatch,
  registerBatchTrigger,
}: {
  items: ExportInvoiceItem[]
  selectable: boolean
  selectedIds: Set<string>
  allSelected: boolean
  toggle: (id: string) => void
  toggleAll: () => void
  openBatch: (id: string, trigger?: HTMLElement) => void
  registerBatchTrigger: (id: string, node: HTMLButtonElement | null) => void
}) {
  return (
    <div className="ops-table-wrap">
      <table className="ops-table export-table">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label="Select all eligible invoices"
                checked={allSelected}
                disabled={!selectable}
                onChange={toggleAll}
              />
            </th>
            <th>Invoice</th>
            <th>Vendor</th>
            <th>Approved by</th>
            <th>Approved</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Issue</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={`${item.id}-${item.batch_id ?? ''}`}
              className={selectedIds.has(item.id) ? 'is-selected' : ''}
            >
              <td>
                <input
                  type="checkbox"
                  aria-label={`Select ${item.invoice_label}`}
                  checked={selectedIds.has(item.id)}
                  disabled={!selectable || !isExportReady(item)}
                  onChange={() => toggle(item.id)}
                />
              </td>
              <td>
                <Link className="ops-link" to={`/review/${item.id}`}>
                  {item.invoice_label}
                </Link>
                <small>{item.filename}</small>
              </td>
              <td>{item.vendor_name || '-'}</td>
              <td>{item.approved_by || '-'}</td>
              <td>{formatDate(item.approved_at)}</td>
              <td>{formatMoney(item.total, item.currency)}</td>
              <td>
                <ExportStatus value={item.status} />
              </td>
              <td className={item.issue ? 'is-issue' : ''}>{item.issue || '-'}</td>
              <td>
                {item.batch_id ? (
                  <button
                    ref={(node) => registerBatchTrigger(item.batch_id!, node)}
                    className="ops-link"
                    onClick={(event) => openBatch(item.batch_id!, event.currentTarget)}
                  >
                    View
                  </button>
                ) : (
                  <Link className="ops-link" to={`/review/${item.id}`}>
                    {item.status === 'ready'
                      ? 'Inspect'
                      : item.status === 'blocked'
                        ? 'Resolve'
                        : 'View'}{' '}
                    <ExternalLink size={13} />
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ExportStatus({ value }: { value: ExportInvoiceItem['status'] }) {
  const labels = {
    ready: 'Ready',
    in_batch: 'In batch',
    exported: 'Exported',
    blocked: 'Blocked',
    drafts: 'Draft',
  }
  const tones = {
    ready: 'info',
    in_batch: 'warning',
    exported: 'success',
    blocked: 'danger',
    drafts: 'purple',
  } as const
  return <StatusBadge tone={tones[value]}>{labels[value]}</StatusBadge>
}
