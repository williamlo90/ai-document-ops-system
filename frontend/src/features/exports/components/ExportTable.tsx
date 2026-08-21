import { ExternalLink, LoaderCircle, RefreshCw, Upload } from 'lucide-react'
import { Link } from 'react-router'
import { formatDate, formatMoney } from '../../../shared/format'
import { StatusBadge } from '../../../shared/ui'
import type { ERPDelivery, ExportInvoiceItem } from '../types'
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
  erpEnabled,
  erpAction,
}: {
  items: ExportInvoiceItem[]
  selectable: boolean
  selectedIds: Set<string>
  allSelected: boolean
  toggle: (id: string) => void
  toggleAll: () => void
  openBatch: (id: string, trigger?: HTMLElement) => void
  registerBatchTrigger: (id: string, node: HTMLButtonElement | null) => void
  erpEnabled: boolean
  erpAction: {
    pendingDocumentId: string | null
    error: Error | null
    run: (documentId: string, action: 'create' | 'reconcile') => void
  }
}) {
  return (
    <div className="ops-table-wrap">
      {erpEnabled && erpAction.error ? (
        <div className="export-inline-error" role="alert">
          {erpAction.error.message}
        </div>
      ) : null}
      <table className={`ops-table export-table ${erpEnabled ? 'is-erp' : ''}`}>
        <thead>
          <tr>
            {!erpEnabled ? (
              <th>
                <input
                  type="checkbox"
                  aria-label="Select all eligible invoices"
                  checked={allSelected}
                  disabled={!selectable}
                  onChange={toggleAll}
                />
              </th>
            ) : null}
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
              {!erpEnabled ? (
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select ${item.invoice_label}`}
                    checked={selectedIds.has(item.id)}
                    disabled={!selectable || !isExportReady(item)}
                    onChange={() => toggle(item.id)}
                  />
                </td>
              ) : null}
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
                {erpEnabled && item.erp_delivery ? (
                  <ERPDeliveryStatus delivery={item.erp_delivery} />
                ) : (
                  <ExportStatus value={item.status} />
                )}
              </td>
              <td className={item.issue || item.erp_delivery?.error_message ? 'is-issue' : ''}>
                {item.erp_delivery?.error_message || item.issue || '-'}
              </td>
              <td>
                {erpEnabled && item.erp_delivery ? (
                  <ERPDeliveryAction
                    item={item}
                    delivery={item.erp_delivery}
                    pending={erpAction.pendingDocumentId === item.id}
                    run={erpAction.run}
                  />
                ) : item.batch_id ? (
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

function ERPDeliveryAction({
  item,
  delivery,
  pending,
  run,
}: {
  item: ExportInvoiceItem
  delivery: ERPDelivery
  pending: boolean
  run: (documentId: string, action: 'create' | 'reconcile') => void
}) {
  if (delivery.status === 'succeeded' && delivery.external_url) {
    return (
      <a
        className="ops-link erp-delivery-action"
        href={delivery.external_url}
        target="_blank"
        rel="noreferrer"
      >
        Open in ERPNext <ExternalLink size={13} />
      </a>
    )
  }
  if (delivery.can_create || delivery.can_retry) {
    return (
      <button
        className="ops-button ops-button--secondary erp-delivery-action"
        disabled={pending}
        onClick={() => run(item.id, 'create')}
      >
        {pending ? (
          <LoaderCircle className="spin" size={15} />
        ) : delivery.can_retry ? (
          <RefreshCw size={15} />
        ) : (
          <Upload size={15} />
        )}
        {pending ? 'Creating...' : delivery.can_retry ? 'Retry' : 'Create ERP draft'}
      </button>
    )
  }
  if (delivery.can_reconcile) {
    return (
      <button
        className="ops-button ops-button--secondary erp-delivery-action"
        disabled={pending}
        onClick={() => run(item.id, 'reconcile')}
      >
        {pending ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}
        {pending ? 'Checking...' : 'Check ERP status'}
      </button>
    )
  }
  return (
    <Link className="ops-link" to={`/review/${item.id}`}>
      Review issue <ExternalLink size={13} />
    </Link>
  )
}

function ERPDeliveryStatus({ delivery }: { delivery: ERPDelivery }) {
  const tone = {
    ready: 'info',
    not_ready: 'neutral',
    pending: 'warning',
    unknown: 'warning',
    failed_retryable: 'danger',
    failed_permanent: 'danger',
    succeeded: 'success',
  } as const
  return <StatusBadge tone={tone[delivery.status]}>{delivery.label}</StatusBadge>
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
