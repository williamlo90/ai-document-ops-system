import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  ExternalLink,
  FileDown,
  ListChecks,
  LoaderCircle,
  Play,
  RotateCcw,
  Save,
  X,
} from 'lucide-react'
import { api } from '../api/client'
import { formatDate, formatMoney } from '../features/invoices/format'
import type {
  ExportBatch,
  ExportBatchMutationResponse,
  ExportInvoiceItem,
  ExportRun,
  ExportWorkspaceResponse,
} from '../features/exports/types'
import {
  Button,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  SearchField,
  SkeletonRows,
  StatusBadge,
} from '../shared/ui'

const pageSize = 10

export function ExportsPage() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const view = params.get('status') ?? 'ready'
  const search = params.get('search') ?? ''
  const vendor = params.get('vendor') ?? ''
  const currency = params.get('currency') ?? ''
  const approver = params.get('approved_by') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const batchId = params.get('batch')
  const [searchValue, setSearchValue] = useState(search)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchOpen, setBatchOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [expandedInvoices, setExpandedInvoices] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [localBatch, setLocalBatch] = useState<ExportBatch | null>(null)

  useEffect(() => setSearchValue(search), [search])
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (searchValue !== search)
        updateParams(params, setParams, { search: searchValue || null, page: null })
    }, 250)
    return () => window.clearTimeout(timeout)
  }, [params, search, searchValue, setParams])
  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 3600)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const queryString = new URLSearchParams({ view, page: String(page), page_size: String(pageSize) })
  if (search) queryString.set('search', search)
  if (vendor) queryString.set('vendor', vendor)
  if (currency) queryString.set('currency', currency)
  if (approver) queryString.set('approved_by', approver)
  if (batchId) queryString.set('batch_id', batchId)
  const workspace = useQuery({
    queryKey: ['export-workspace', queryString.toString()],
    queryFn: () => api<ExportWorkspaceResponse>(`/exports/workspace?${queryString}`),
    refetchInterval: 15_000,
  })
  const selectedItems = useMemo(
    () => workspace.data?.items.filter((item) => selectedIds.has(item.id)) ?? [],
    [selectedIds, workspace.data?.items],
  )
  const selectedAmount = selectedItems.reduce((total, item) => total + Number(item.total ?? 0), 0)
  const selectedCurrencies = new Set(selectedItems.map((item) => item.currency).filter(Boolean))
  const selectedCurrency = selectedCurrencies.size === 1 ? [...selectedCurrencies][0] : null

  const createBatch = useMutation({
    mutationFn: (mode: 'ready' | 'draft') =>
      api<ExportBatchMutationResponse>('/exports/batches', {
        method: 'POST',
        body: JSON.stringify({ document_ids: [...selectedIds], mode }),
      }),
    onSuccess: (result, mode) => {
      setLocalBatch(result.batch)
      setSelectedIds(new Set())
      setBatchOpen(true)
      updateParams(params, setParams, {
        batch: result.batch.id,
        status: mode === 'draft' ? 'drafts' : 'in_batch',
        page: null,
      })
      setToast(
        mode === 'draft'
          ? `Draft saved with ${result.accepted.length} invoices.`
          : `${result.accepted.length} invoices added to export batch.`,
      )
      void queryClient.invalidateQueries({ queryKey: ['export-workspace'] })
    },
  })
  const saveBatch = useMutation({
    mutationFn: (batch: ExportBatch) =>
      api<ExportBatchMutationResponse>(`/exports/batches/${batch.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          document_ids: batch.invoices.map((item) => item.id),
          mode: 'draft',
          name: batch.name,
        }),
      }),
    onSuccess: (result) => {
      setLocalBatch(result.batch)
      updateParams(params, setParams, { batch: result.batch.id, status: 'drafts' })
      setToast('Export draft saved.')
      void queryClient.invalidateQueries({ queryKey: ['export-workspace'] })
    },
  })
  const executeBatch = useMutation({
    mutationFn: (batch: ExportBatch) =>
      api<{ run: ExportRun }>(`/exports/batches/${batch.id}/execute`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      }),
    onSuccess: (result) => {
      setConfirmOpen(false)
      setRunId(result.run.id)
      setToast(`${result.run.invoice_count} invoices exported successfully.`)
      updateParams(params, setParams, { status: 'exported' })
      void queryClient.invalidateQueries({ queryKey: ['export-workspace'] })
    },
  })

  const batch = workspace.data?.batch ?? localBatch
  const allChecksPassed =
    Boolean(batch?.invoice_count) && batch?.eligibility.every((check) => check.state === 'passed')
  const setView = (next: string) => {
    setSelectedIds(new Set())
    updateParams(params, setParams, { status: next, page: null })
  }
  const toggleSelection = (id: string) =>
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const selectable = workspace.data?.items.filter((item) => item.status === 'ready') ?? []
  const allSelected = selectable.length > 0 && selectable.every((item) => selectedIds.has(item.id))

  return (
    <div className="ops-page exports-page">
      <PageHeader
        title="Exports"
        description="Select approved invoices, verify eligibility, and create a controlled export."
      />
      {workspace.error ? (
        <ErrorState
          message={(workspace.error as Error).message}
          retry={() => void workspace.refetch()}
        />
      ) : (
        <div className={`export-page-layout ${batch || selectedIds.size ? 'has-batch' : ''}`}>
          <div className="export-primary">
            <ExportTabs data={workspace.data} active={view} setView={setView} />
            <Panel className="export-library">
              <div className="export-toolbar">
                <SearchField
                  value={searchValue}
                  onChange={setSearchValue}
                  placeholder={`Search ${view.replace('_', ' ')} invoices...`}
                  label="Search export invoices"
                />
                <select
                  aria-label="Vendor"
                  value={vendor}
                  onChange={(event) =>
                    updateParams(params, setParams, {
                      vendor: event.target.value || null,
                      page: null,
                    })
                  }
                >
                  <option value="">All vendors</option>
                  {workspace.data?.filters.vendors.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
                <select
                  aria-label="Currency"
                  value={currency}
                  onChange={(event) =>
                    updateParams(params, setParams, {
                      currency: event.target.value || null,
                      page: null,
                    })
                  }
                >
                  <option value="">All currencies</option>
                  {workspace.data?.filters.currencies.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
                <select
                  aria-label="Approved by"
                  value={approver}
                  onChange={(event) =>
                    updateParams(params, setParams, {
                      approved_by: event.target.value || null,
                      page: null,
                    })
                  }
                >
                  <option value="">All approvers</option>
                  {workspace.data?.filters.approvers.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </div>
              {selectedIds.size ? (
                <div className="export-selection-bar" role="status">
                  <span>
                    <CheckCircle2 size={16} />
                    <strong>{selectedIds.size}</strong> selected
                  </span>
                  <button className="ops-link" onClick={() => setSelectedIds(new Set())}>
                    Clear selection
                  </button>
                  <Button
                    onClick={() => createBatch.mutate('ready')}
                    disabled={createBatch.isPending}
                  >
                    {createBatch.isPending ? (
                      <LoaderCircle className="spin" size={16} />
                    ) : (
                      <FileDown size={16} />
                    )}{' '}
                    Add to export
                  </Button>
                </div>
              ) : null}
              {workspace.isLoading ? (
                <SkeletonRows count={8} />
              ) : workspace.data?.items.length ? (
                <ExportTable
                  items={workspace.data.items}
                  selectable={view === 'ready'}
                  selectedIds={selectedIds}
                  allSelected={allSelected}
                  toggle={toggleSelection}
                  toggleAll={() =>
                    setSelectedIds(
                      allSelected ? new Set() : new Set(selectable.map((item) => item.id)),
                    )
                  }
                  openBatch={(id) => {
                    updateParams(params, setParams, { batch: id, status: 'in_batch' })
                    setBatchOpen(true)
                  }}
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
                      <Link
                        className="ops-button ops-button--secondary"
                        to="/inbox?state=needs-decision"
                      >
                        View inbox
                      </Link>
                    ) : null
                  }
                />
              )}
              {workspace.data ? (
                <footer className="ops-pagination">
                  <span>
                    Showing page {workspace.data.page} of {workspace.data.total_pages} /{' '}
                    {workspace.data.total} invoices
                  </span>
                  <div>
                    <Button
                      variant="ghost"
                      disabled={page <= 1}
                      onClick={() => updateParams(params, setParams, { page: String(page - 1) })}
                    >
                      Previous
                    </Button>
                    <strong>{page}</strong>
                    <Button
                      variant="ghost"
                      disabled={page >= workspace.data.total_pages}
                      onClick={() => updateParams(params, setParams, { page: String(page + 1) })}
                    >
                      Next
                    </Button>
                  </div>
                </footer>
              ) : null}
            </Panel>
          </div>
          {batch || selectedIds.size ? (
            <ExportBatchPanel
              batch={batch}
              selectedItems={selectedItems}
              selectedAmount={selectedAmount}
              selectedCurrency={selectedCurrency}
              open={batchOpen}
              loading={workspace.isLoading && !batch}
              mutationError={
                (createBatch.error || saveBatch.error || executeBatch.error) as Error | null
              }
              expanded={expandedInvoices}
              setExpanded={setExpandedInvoices}
              close={() => setBatchOpen(false)}
              saveDraft={() => (batch ? saveBatch.mutate(batch) : createBatch.mutate('draft'))}
              execute={() => setConfirmOpen(true)}
              canExecute={Boolean(allChecksPassed && batch?.status === 'ready')}
              recentRuns={workspace.data?.recent_runs ?? []}
              openRun={setRunId}
            />
          ) : null}
        </div>
      )}
      {confirmOpen && batch ? (
        <ConfirmExport
          batch={batch}
          pending={executeBatch.isPending}
          close={() => setConfirmOpen(false)}
          confirm={() => executeBatch.mutate(batch)}
        />
      ) : null}
      {runId ? (
        <RunDrawer
          runId={runId}
          close={() => setRunId(null)}
          refresh={() => void queryClient.invalidateQueries({ queryKey: ['export-workspace'] })}
        />
      ) : null}
      {toast ? (
        <div className="ops-toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      ) : null}
    </div>
  )
}

function ExportTabs({
  data,
  active,
  setView,
}: {
  data?: ExportWorkspaceResponse
  active: string
  setView: (view: string) => void
}) {
  const tabs = [
    ['ready', 'Ready'],
    ['in_batch', 'In batch'],
    ['exported', 'Exported'],
    ['blocked', 'Blocked'],
    ['drafts', 'Drafts'],
  ]
  return (
    <div className="export-tabs" role="tablist" aria-label="Export status">
      {tabs.map(([key, label]) => {
        const count =
          key === 'drafts'
            ? active === 'drafts'
              ? data?.total
              : null
            : data?.summary[key as keyof ExportWorkspaceResponse['summary']]?.count
        return (
          <button
            key={key}
            role="tab"
            aria-selected={active === key}
            className={active === key ? 'is-active' : ''}
            onClick={() => setView(key)}
          >
            {label}
            {count == null ? null : <span>{count}</span>}
          </button>
        )
      })}
    </div>
  )
}

function ExportTable({
  items,
  selectable,
  selectedIds,
  allSelected,
  toggle,
  toggleAll,
  openBatch,
}: {
  items: ExportInvoiceItem[]
  selectable: boolean
  selectedIds: Set<string>
  allSelected: boolean
  toggle: (id: string) => void
  toggleAll: () => void
  openBatch: (id: string) => void
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
                  disabled={!selectable || item.status !== 'ready'}
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
                  <button className="ops-link" onClick={() => openBatch(item.batch_id!)}>
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

function ExportBatchPanel({
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
}: {
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
}) {
  const invoices = batch?.invoices ?? selectedItems
  const count = batch?.invoice_count ?? selectedItems.length
  const amount = batch ? batch.total_amount : selectedCurrency ? String(selectedAmount) : null
  const currency = batch?.currency ?? selectedCurrency
  const completedRun = batch?.last_run_id
    ? recentRuns.find((run) => run.id === batch.last_run_id)
    : undefined
  return (
    <aside className={`export-batch-panel ${open ? 'is-open' : ''}`} aria-label="Export batch">
      <header>
        <h2>Export batch</h2>
        <button
          className="ops-icon-button export-batch-close"
          aria-label="Close export batch"
          onClick={close}
        >
          <X size={19} />
        </button>
      </header>
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
    </aside>
  )
}

function ConfirmExport({
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

function RunDrawer({
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

function updateParams(
  current: URLSearchParams,
  setter: ReturnType<typeof useSearchParams>[1],
  values: Record<string, string | null | undefined>,
) {
  const next = new URLSearchParams(current)
  for (const [key, value] of Object.entries(values)) {
    if (value) next.set(key, value)
    else next.delete(key)
  }
  setter(next, { replace: false })
}
