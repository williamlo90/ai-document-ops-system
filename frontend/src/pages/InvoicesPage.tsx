import { useCallback, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { CheckCircle2, Upload, X } from 'lucide-react'
import { api } from '../api/client'
import { useShell } from '../app/shell-context'
import { CorrectionDialog } from '../features/invoices/components/CorrectionDialog'
import { InvoiceInspector } from '../features/invoices/components/InvoiceInspector'
import { InvoiceLibrary } from '../features/invoices/components/InvoiceLibrary'
import { UploadInvoiceDialog } from '../features/invoices/components/UploadInvoiceDialog'
import {
  isInvoiceLifecycleFilter,
  type InvoiceLifecycleFilter,
} from '../features/invoices/selectors'
import type { InvoiceDetailResponse, InvoiceListResponse } from '../features/invoices/types'
import { updateSearchParams } from '../shared/searchParams'
import { Button, ErrorState, PageHeader } from '../shared/ui'

const pageSize = 10

export function InvoicesPage() {
  const { role } = useShell()
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [correctionOpen, setCorrectionOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const invoiceTriggers = useRef(new Map<string, HTMLButtonElement>())
  const returnFocusId = useRef<string | null>(null)
  const search = params.get('search') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const requestedStatus = params.get('status')
  const status: InvoiceLifecycleFilter = isInvoiceLifecycleFilter(requestedStatus)
    ? requestedStatus
    : ''
  const vendor = params.get('vendor') ?? ''
  const sort = params.get('sort') ?? 'updated'
  const direction = params.get('direction') ?? 'desc'
  const selectedId = params.get('invoice')
  const queryString = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort,
    direction,
  })
  if (search) queryString.set('search', search)
  if (status) queryString.set('status', status)
  if (vendor) queryString.set('vendor', vendor)
  const invoices = useQuery({
    queryKey: ['invoices', queryString.toString()],
    queryFn: () => api<InvoiceListResponse>(`/invoices?${queryString}`),
    refetchInterval: 10_000,
  })
  const selected = invoices.data?.items.find((invoice) => invoice.id === selectedId) ?? null
  const detail = useQuery({
    queryKey: ['invoice-detail', selected?.id],
    queryFn: () => api<InvoiceDetailResponse>(`/documents/${selected?.id}`),
    enabled: Boolean(selected?.id),
  })

  const setFilter = (key: string, value?: string) =>
    updateSearchParams(params, setParams, {
      [key]: value || null,
      page: null,
      ...(key !== 'invoice' ? { invoice: null } : {}),
    })
  const openInspector = useCallback(
    (id: string) => {
      returnFocusId.current = id
      updateSearchParams(params, setParams, { invoice: id })
    },
    [params, setParams],
  )
  const closeInspector = useCallback(() => {
    updateSearchParams(params, setParams, { invoice: null })
    const trigger = returnFocusId.current
      ? invoiceTriggers.current.get(returnFocusId.current)
      : null
    queueMicrotask(() => trigger?.focus())
  }, [params, setParams])

  return (
    <div className="ops-page invoices-page">
      {notice ? (
        <div className="ops-toast" role="status">
          <CheckCircle2 size={18} />
          <span>{notice}</span>
          <button aria-label="Close message" onClick={() => setNotice('')}>
            <X size={15} />
          </button>
        </div>
      ) : null}
      <PageHeader
        title="Invoices"
        description="Find, track, and inspect every invoice in one place."
        action={
          role !== 'reviewer' ? (
            <Button variant="primary" onClick={() => setUploadOpen(true)}>
              <Upload size={16} /> Upload invoice
            </Button>
          ) : null
        }
      />
      {invoices.error ? (
        <ErrorState
          message={(invoices.error as Error).message}
          retry={() => void invoices.refetch()}
        />
      ) : (
        <div className={`invoice-master-detail ${selected ? 'has-selection' : ''}`}>
          <InvoiceLibrary
            data={invoices.data}
            loading={invoices.isLoading}
            selectedId={selected?.id}
            status={status}
            search={search}
            vendor={vendor}
            sort={sort}
            direction={direction}
            setFilter={setFilter}
            setSort={(nextSort, nextDirection) =>
              updateSearchParams(params, setParams, {
                sort: nextSort,
                direction: nextDirection,
                page: null,
              })
            }
            select={openInspector}
            registerTrigger={(id, node) => {
              if (node) invoiceTriggers.current.set(id, node)
              else invoiceTriggers.current.delete(id)
            }}
          />
          {selected ? (
            <InvoiceInspector
              invoice={selected}
              detail={detail.data}
              loading={detail.isLoading}
              error={detail.error as Error | null}
              reviewable={role !== 'uploader'}
              correctable={
                role === 'uploader' &&
                selected.business_status === 'needs_correction' &&
                Boolean(detail.data?.extraction)
              }
              correct={() => setCorrectionOpen(true)}
              close={closeInspector}
            />
          ) : null}
        </div>
      )}
      {uploadOpen ? (
        <UploadInvoiceDialog
          close={() => setUploadOpen(false)}
          completed={() => {
            setUploadOpen(false)
            void queryClient.invalidateQueries({ queryKey: ['invoices'] })
          }}
        />
      ) : null}
      {correctionOpen && selected && detail.data?.extraction ? (
        <CorrectionDialog
          invoice={selected}
          extraction={detail.data.extraction}
          close={() => setCorrectionOpen(false)}
          completed={async () => {
            setCorrectionOpen(false)
            setNotice('Correction sent back to the reviewer.')
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ['invoices'] }),
              queryClient.invalidateQueries({ queryKey: ['invoice-detail', selected.id] }),
              queryClient.invalidateQueries({ queryKey: ['workspace'] }),
            ])
          }}
        />
      ) : null}
    </div>
  )
}
