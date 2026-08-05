import type { ReactNode } from 'react'
import { AlertCircle, ArrowRight, CheckCircle2, Clock3 } from 'lucide-react'
import { Link } from 'react-router'
import { formatMoney } from '../../../shared/format'
import { invoiceLabel } from '../../invoices/format'
import type { ExceptionItem } from '../../exceptions/types'
import type { ReviewQueueItem } from '../../review/types'
import { Button, EmptyState, StatusBadge } from '../../../shared/ui'
import { categoryLabels } from '../selectors'

export function InboxSummary({
  icon,
  value,
  label,
  tone = 'neutral',
}: {
  icon: ReactNode
  value: number
  label: string
  tone?: 'neutral' | 'warning' | 'danger'
}) {
  return (
    <div className={`inbox-summary-item is-${tone}`}>
      <span>{icon}</span>
      <strong>{value}</strong>
      <small>{label}</small>
    </div>
  )
}

export function DecisionTable({ items }: { items: ReviewQueueItem[] }) {
  if (!items.length)
    return (
      <EmptyState
        title="No invoices need a decision"
        body="Invoices will appear here when validation passes and a reviewer decision is required."
      />
    )
  return (
    <div className="ops-table-wrap">
      <table className="ops-table inbox-table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Vendor</th>
            <th>Amount</th>
            <th>Issue</th>
            <th>Risk</th>
            <th>Waiting</th>
            <th>Owner</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <strong>{invoiceLabel(item)}</strong>
                <small>{item.original_filename}</small>
              </td>
              <td>{item.vendor_name || 'Not detected'}</td>
              <td>{formatMoney(item.total, item.currency)}</td>
              <td>
                {item.finding || (
                  <span className="inbox-clear">
                    <CheckCircle2 size={14} /> No blocker
                  </span>
                )}
              </td>
              <td>
                <Risk risk={item.risk} />
              </td>
              <td>
                <Clock3 size={13} /> {age(item.age_seconds)}
              </td>
              <td>{item.owner || 'Unassigned'}</td>
              <td>
                <Link
                  className="ops-button ops-button--secondary"
                  to={`/review/${item.id}?from=inbox`}
                >
                  Review <ArrowRight size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function BlockedTable({ items }: { items: ExceptionItem[] }) {
  if (!items.length)
    return (
      <EmptyState
        title="No blocked invoices"
        body="Approval blockers will appear here with the validation issue that must be resolved."
      />
    )
  return (
    <div className="ops-table-wrap">
      <table className="ops-table inbox-table">
        <thead>
          <tr>
            <th>Issue</th>
            <th>Invoice</th>
            <th>Vendor</th>
            <th>Risk</th>
            <th>Waiting</th>
            <th>Owner</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <td>
                <strong className="inbox-issue">
                  <AlertCircle size={14} />
                  {item.issue}
                </strong>
                <small>{categoryLabels[item.category]}</small>
              </td>
              <td>{item.invoice_number || item.original_filename}</td>
              <td>{item.vendor_name || 'Not detected'}</td>
              <td>
                <Risk risk={item.risk} />
              </td>
              <td>
                <Clock3 size={13} /> {age(item.age_seconds)}
              </td>
              <td>{item.owner || 'Unassigned'}</td>
              <td>
                <Link
                  className="ops-button ops-button--secondary"
                  to={`/review/${item.document_id}?from=inbox&state=blocked&exception=${item.id}`}
                >
                  Resolve <ArrowRight size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function InboxPagination({
  page,
  pages,
  total,
  setPage,
}: {
  page: number
  pages: number
  total: number
  setPage: (page: number) => void
}) {
  return (
    <footer className="ops-pagination">
      <span>
        {total} result{total === 1 ? '' : 's'}
      </span>
      <div>
        <Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </Button>
        <strong>
          {page} / {pages}
        </strong>
        <Button variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </Button>
      </div>
    </footer>
  )
}

function Risk({ risk }: { risk: 'high' | 'medium' | 'low' }) {
  return (
    <StatusBadge tone={risk === 'high' ? 'danger' : risk === 'medium' ? 'warning' : 'info'}>
      {risk[0].toUpperCase() + risk.slice(1)}
    </StatusBadge>
  )
}

function age(seconds: number): string {
  if (seconds < 3600) return `${Math.max(1, Math.floor(seconds / 60))}m`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`
  return `${Math.floor(seconds / 86400)}d`
}
