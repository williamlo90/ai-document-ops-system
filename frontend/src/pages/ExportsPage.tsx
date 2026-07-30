import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { CheckCircle2 } from 'lucide-react'
import { api } from '../api/client'
import { ExportBatchPanel } from '../features/exports/components/ExportBatchPanel'
import { ConfirmExport } from '../features/exports/components/ConfirmExport'
import { ExportWorkspace } from '../features/exports/components/ExportWorkspace'
import { RunDrawer } from '../features/exports/components/RunDrawer'
import { isExportReady, isExportView, type ExportView } from '../features/exports/selectors'
import type {
  ExportBatch,
  ExportBatchMutationResponse,
  ExportRun,
  ExportWorkspaceResponse,
} from '../features/exports/types'
import { updateSearchParams } from '../shared/searchParams'
import { PageHeader } from '../shared/ui'

const pageSize = 10

export function ExportsPage() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const requestedView = params.get('status')
  const view: ExportView = isExportView(requestedView) ? requestedView : 'ready'
  const search = params.get('search') ?? ''
  const vendor = params.get('vendor') ?? ''
  const currency = params.get('currency') ?? ''
  const approver = params.get('approved_by') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const batchId = params.get('batch')
  const [searchValue, setSearchValue] = useState(search)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchOpen, setBatchOpen] = useState(Boolean(batchId))
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [expandedInvoices, setExpandedInvoices] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [localBatch, setLocalBatch] = useState<ExportBatch | null>(null)
  const batchReturnFocus = useRef<HTMLElement | null>(null)
  const batchTriggers = useRef(new Map<string, HTMLButtonElement>())

  useEffect(() => setSearchValue(search), [search])
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (searchValue !== search)
        updateSearchParams(params, setParams, { search: searchValue || null, page: null })
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
      updateSearchParams(params, setParams, {
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
      updateSearchParams(params, setParams, { batch: result.batch.id, status: 'drafts' })
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
      updateSearchParams(params, setParams, { status: 'exported' })
      void queryClient.invalidateQueries({ queryKey: ['export-workspace'] })
    },
  })

  const batch = workspace.data?.batch ?? localBatch
  const allChecksPassed =
    Boolean(batch?.invoice_count) && batch?.eligibility.every((check) => check.state === 'passed')
  const selectable = workspace.data?.items.filter(isExportReady) ?? []
  const allSelected = selectable.length > 0 && selectable.every((item) => selectedIds.has(item.id))

  const setView = (next: ExportView) => {
    setSelectedIds(new Set())
    updateSearchParams(params, setParams, { status: next, page: null })
  }
  const closeBatch = useCallback(() => {
    setBatchOpen(false)
    const trigger =
      batchReturnFocus.current ??
      document.querySelector<HTMLElement>('.export-tabs [aria-selected="true"]')
    queueMicrotask(() => {
      if (trigger?.isConnected) trigger.focus()
    })
  }, [])
  const openExistingBatch = useCallback(
    (id: string, trigger?: HTMLElement) => {
      batchReturnFocus.current = trigger ?? batchTriggers.current.get(id) ?? null
      updateSearchParams(params, setParams, { batch: id, status: 'in_batch' })
      setBatchOpen(true)
    },
    [params, setParams],
  )
  const toggleSelection = (id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="ops-page exports-page">
      <PageHeader
        title="Exports"
        description="Select approved invoices, verify eligibility, and create a controlled export."
      />
      <div className={`export-page-layout ${batch || selectedIds.size ? 'has-batch' : ''}`}>
        <ExportWorkspace
          data={workspace.data}
          error={workspace.error as Error | null}
          loading={workspace.isLoading}
          view={view}
          page={page}
          filters={{ search: searchValue, vendor, currency, approver }}
          selection={{
            ids: selectedIds,
            pending: createBatch.isPending,
            allSelected,
            clear: () => setSelectedIds(new Set()),
            saveDraft: () => createBatch.mutate('draft'),
            createBatch: () => createBatch.mutate('ready'),
            toggle: toggleSelection,
            toggleAll: () =>
              setSelectedIds(
                allSelected ? new Set<string>() : new Set(selectable.map((item) => item.id)),
              ),
          }}
          retry={() => void workspace.refetch()}
          setView={setView}
          setSearch={setSearchValue}
          setFilter={(values) => updateSearchParams(params, setParams, values)}
          openBatch={openExistingBatch}
          registerBatchTrigger={(id, node) => {
            if (node) batchTriggers.current.set(id, node)
            else batchTriggers.current.delete(id)
          }}
        />
        {!workspace.error && batch ? (
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
            close={closeBatch}
            saveDraft={() => saveBatch.mutate(batch)}
            execute={() => setConfirmOpen(true)}
            canExecute={Boolean(allChecksPassed && batch.status === 'ready')}
            recentRuns={workspace.data?.recent_runs ?? []}
            openRun={setRunId}
          />
        ) : null}
      </div>
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
