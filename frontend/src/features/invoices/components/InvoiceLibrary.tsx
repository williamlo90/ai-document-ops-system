import { formatDate, formatMoney } from '../../../shared/format'
import { invoiceLabel } from '../format'
import { invoiceStatus, invoiceTabs, type InvoiceLifecycleFilter } from '../selectors'
import type { InvoiceItem, InvoiceListResponse } from '../types'
import {
  Button,
  EmptyState,
  Panel,
  SearchField,
  SkeletonRows,
  StatusBadge,
} from '../../../shared/ui'

export type InvoiceLibraryProps = {
  data?: InvoiceListResponse
  loading: boolean
  selectedId?: string
  status: InvoiceLifecycleFilter
  search: string
  vendor: string
  sort: string
  direction: string
  setFilter: (key: string, value?: string) => void
  setSort: (sort: string, direction: string) => void
  select: (id: string) => void
  registerTrigger: (id: string, node: HTMLButtonElement | null) => void
}

export function InvoiceLibrary({
  data,
  loading,
  selectedId,
  status,
  search,
  vendor,
  sort,
  direction,
  setFilter,
  setSort,
  select,
  registerTrigger,
}: InvoiceLibraryProps) {
  return (
    <Panel className="invoice-library">
      <div className="invoice-lifecycle-tabs" role="tablist" aria-label="Invoice status">
        {invoiceTabs(data?.summary).map((item) => (
          <button
            role="tab"
            aria-selected={status === item.value}
            key={item.label}
            className={status === item.value ? 'is-active' : ''}
            onClick={() => setFilter('status', item.value)}
            onFocus={(event) =>
              event.currentTarget.scrollIntoView({ block: 'nearest', inline: 'center' })
            }
          >
            {item.label}
            <span>{item.count}</span>
          </button>
        ))}
      </div>
      <div className="invoice-toolbar">
        <SearchField
          value={search}
          onChange={(value) => setFilter('search', value)}
          placeholder="Search invoices..."
          label="Search invoices"
        />
        <input
          className="ops-filter-input"
          aria-label="Vendor filter"
          value={vendor}
          onChange={(event) => setFilter('vendor', event.target.value)}
          placeholder="Vendor"
        />
        <select
          aria-label="Sort invoices"
          value={`${sort}:${direction}`}
          onChange={(event) => {
            const [nextSort, nextDirection] = event.target.value.split(':')
            setSort(nextSort, nextDirection)
          }}
        >
          <option value="updated:desc">Recently updated</option>
          <option value="invoice_date:desc">Invoice date</option>
          <option value="amount:desc">Amount: high to low</option>
          <option value="vendor:asc">Vendor: A-Z</option>
        </select>
      </div>
      {loading ? (
        <SkeletonRows count={8} />
      ) : data?.items.length ? (
        <InvoiceTable
          items={data.items}
          selectedId={selectedId}
          select={select}
          registerTrigger={registerTrigger}
        />
      ) : (
        <EmptyState title="No invoices found" body="Try clearing the current search or filters." />
      )}
      {data ? (
        <Pagination
          page={data.page}
          pages={data.total_pages}
          total={data.total}
          setPage={(value) => setFilter('page', String(value))}
        />
      ) : null}
    </Panel>
  )
}

function InvoiceTable({
  items,
  selectedId,
  select,
  registerTrigger,
}: {
  items: InvoiceItem[]
  selectedId?: string
  select: (id: string) => void
  registerTrigger: (id: string, node: HTMLButtonElement | null) => void
}) {
  return (
    <div className="ops-table-wrap">
      <table className="ops-table invoice-table">
        <thead>
          <tr>
            <th aria-label="Selected" />
            <th>Invoice</th>
            <th>Vendor</th>
            <th>Invoice date</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Owner</th>
            <th>Updated</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((invoice) => {
            const status = invoiceStatus(invoice.business_status)
            return (
              <tr
                key={invoice.id}
                className={selectedId === invoice.id ? 'is-selected' : ''}
                onClick={() => select(invoice.id)}
              >
                <td>
                  <span className="ops-radio" aria-hidden="true">
                    {selectedId === invoice.id ? <i /> : null}
                  </span>
                </td>
                <td>
                  <button
                    ref={(node) => registerTrigger(invoice.id, node)}
                    className="ops-link"
                    onClick={(event) => {
                      event.stopPropagation()
                      select(invoice.id)
                    }}
                  >
                    {invoiceLabel(invoice)}
                  </button>
                  <small className="invoice-source-name">{invoice.original_filename}</small>
                  <small className="invoice-mobile-vendor">
                    {invoice.vendor_name || 'Vendor not detected'}
                  </small>
                </td>
                <td>{invoice.vendor_name || '-'}</td>
                <td>{formatDate(invoice.invoice_date)}</td>
                <td>{formatMoney(invoice.total, invoice.currency)}</td>
                <td>
                  <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                </td>
                <td>
                  <span className="ops-owner">
                    <i>{initials(invoice.current_owner)}</i>
                    {invoice.current_owner}
                  </span>
                </td>
                <td>{formatDate(invoice.updated_at, true)}</td>
                <td>
                  <button
                    className="ops-link"
                    onClick={(event) => {
                      event.stopPropagation()
                      select(invoice.id)
                    }}
                  >
                    View
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Pagination({
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
        Showing page {page} of {pages} / {total} invoices
      </span>
      <div>
        <Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </Button>
        <strong>{page}</strong>
        <Button variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </Button>
      </div>
    </footer>
  )
}

function initials(value: string): string {
  return (
    value
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase() || '?'
  )
}
