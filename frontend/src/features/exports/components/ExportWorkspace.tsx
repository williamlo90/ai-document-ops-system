import { CheckCircle2, FileDown, LoaderCircle, Save } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  Button,
  EmptyState,
  ErrorState,
  Panel,
  SearchField,
  SkeletonRows,
} from '../../../shared/ui'
import type { ExportWorkspaceResponse } from '../types'
import type { ExportView } from '../selectors'
import { ExportTabs } from './ExportTabs'
import { ExportTable } from './ExportTable'

type ExportFilters = {
  search: string
  vendor: string
  currency: string
  approver: string
}

type ExportSelection = {
  ids: Set<string>
  pending: boolean
  allSelected: boolean
  clear: () => void
  saveDraft: () => void
  createBatch: () => void
  toggle: (id: string) => void
  toggleAll: () => void
}

export type ExportWorkspaceProps = {
  data?: ExportWorkspaceResponse
  error: Error | null
  loading: boolean
  view: ExportView
  page: number
  filters: ExportFilters
  selection: ExportSelection
  retry: () => void
  setView: (view: ExportView) => void
  setSearch: (value: string) => void
  setFilter: (values: Record<string, string | null>) => void
  openBatch: (id: string, trigger?: HTMLElement) => void
  registerBatchTrigger: (id: string, node: HTMLButtonElement | null) => void
}

export function ExportWorkspace({
  data,
  error,
  loading,
  view,
  page,
  filters,
  selection,
  retry,
  setView,
  setSearch,
  setFilter,
  openBatch,
  registerBatchTrigger,
}: ExportWorkspaceProps) {
  if (error) return <ErrorState message={error.message} retry={retry} />

  return (
    <div className="export-primary">
      <ExportTabs data={data} active={view} setView={setView} />
      <Panel className="export-library">
        <div className="export-toolbar">
          <SearchField
            value={filters.search}
            onChange={setSearch}
            placeholder={`Search ${view.replace('_', ' ')} invoices...`}
            label="Search export invoices"
          />
          <select
            aria-label="Vendor"
            value={filters.vendor}
            onChange={(event) => setFilter({ vendor: event.target.value || null, page: null })}
          >
            <option value="">All vendors</option>
            {data?.filters.vendors.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <select
            aria-label="Currency"
            value={filters.currency}
            onChange={(event) => setFilter({ currency: event.target.value || null, page: null })}
          >
            <option value="">All currencies</option>
            {data?.filters.currencies.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <select
            aria-label="Approved by"
            value={filters.approver}
            onChange={(event) => setFilter({ approved_by: event.target.value || null, page: null })}
          >
            <option value="">All approvers</option>
            {data?.filters.approvers.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </div>
        {selection.ids.size ? (
          <div className="export-selection-bar" role="status">
            <span>
              <CheckCircle2 size={16} />
              <strong>{selection.ids.size}</strong> selected
            </span>
            <button className="ops-link" onClick={selection.clear}>
              Clear selection
            </button>
            <Button onClick={selection.saveDraft} disabled={selection.pending}>
              <Save size={16} /> Save draft
            </Button>
            <Button onClick={selection.createBatch} disabled={selection.pending}>
              {selection.pending ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <FileDown size={16} />
              )}{' '}
              Add to export
            </Button>
          </div>
        ) : null}
        {loading ? (
          <SkeletonRows count={8} />
        ) : data?.items.length ? (
          <ExportTable
            items={data.items}
            selectable={view === 'ready'}
            selectedIds={selection.ids}
            allSelected={selection.allSelected}
            toggle={selection.toggle}
            toggleAll={selection.toggleAll}
            openBatch={openBatch}
            registerBatchTrigger={registerBatchTrigger}
          />
        ) : (
          <EmptyState
            title={
              view === 'ready'
                ? 'No invoices are ready to export'
                : `No ${view.replace('_', ' ')} invoices found`
            }
            body={
              view === 'ready'
                ? 'Approved invoices without blockers will appear here.'
                : 'Try another status or clear the current filters.'
            }
            action={
              view === 'ready' ? (
                <Link className="ops-button ops-button--secondary" to="/inbox?state=needs-decision">
                  View inbox
                </Link>
              ) : null
            }
          />
        )}
        {data ? (
          <footer className="ops-pagination">
            <span>
              Showing page {data.page} of {data.total_pages} / {data.total} invoices
            </span>
            <div>
              <Button
                variant="ghost"
                disabled={page <= 1}
                onClick={() => setFilter({ page: String(page - 1) })}
              >
                Previous
              </Button>
              <strong>{page}</strong>
              <Button
                variant="ghost"
                disabled={page >= data.total_pages}
                onClick={() => setFilter({ page: String(page + 1) })}
              >
                Next
              </Button>
            </div>
          </footer>
        ) : null}
      </Panel>
    </div>
  )
}
