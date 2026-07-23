import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { AlertCircle, CalendarDays, Inbox as InboxIcon } from 'lucide-react'
import { api } from '../api/client'
import type { ExceptionListResponse } from '../features/exceptions/types'
import {
  BlockedTable,
  DecisionTable,
  InboxPagination,
  InboxSummary,
} from '../features/inbox/components/InboxTables'
import { categoryLabels, type InboxState } from '../features/inbox/selectors'
import type { ReviewWorklist } from '../features/review/types'
import { ErrorState, PageHeader, Panel, SearchField, SkeletonRows } from '../shared/ui'

const pageSize = 12

export function InboxPage() {
  const [params, setParams] = useSearchParams()
  const state: InboxState = params.get('state') === 'blocked' ? 'blocked' : 'needs-decision'
  const search = params.get('search') ?? ''
  const risk = params.get('risk') ?? ''
  const owner = params.get('owner') ?? ''
  const vendor = params.get('vendor') ?? ''
  const category = params.get('category') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const sort = params.get('sort') ?? 'risk'
  const direction = params.get('direction') ?? 'desc'

  const reviewRequest = new URLSearchParams({
    page: String(state === 'needs-decision' ? page : 1),
    page_size: String(pageSize),
    scope: 'decision',
    sort,
    direction,
  })
  if (search && state === 'needs-decision') reviewRequest.set('search', search)
  if (risk && state === 'needs-decision') reviewRequest.set('risk', risk)
  if (owner && state === 'needs-decision') reviewRequest.set('owner', owner)
  if (vendor && state === 'needs-decision') reviewRequest.set('vendor', vendor)

  const exceptionRequest = new URLSearchParams({
    page: String(state === 'blocked' ? page : 1),
    page_size: String(pageSize),
    scope: 'blocking',
    sort,
    direction,
  })
  if (search && state === 'blocked') exceptionRequest.set('search', search)
  if (risk && state === 'blocked') exceptionRequest.set('risk', risk)
  if (owner && state === 'blocked') exceptionRequest.set('owner', owner)
  if (category && state === 'blocked') exceptionRequest.set('category', category)

  const review = useQuery({
    queryKey: ['review-worklist-v2', reviewRequest.toString()],
    queryFn: () => api<ReviewWorklist>(`/review/worklist?${reviewRequest}`),
    refetchInterval: 10_000,
  })
  const blocked = useQuery({
    queryKey: ['exceptions', exceptionRequest.toString()],
    queryFn: () => api<ExceptionListResponse>(`/exceptions?${exceptionRequest}`),
    refetchInterval: 10_000,
  })
  const current = state === 'blocked' ? blocked : review
  const setFilter = (values: Record<string, string | null | undefined>) =>
    updateParams(params, setParams, { ...values, page: null })
  const selectState = (value: InboxState) =>
    updateParams(params, setParams, {
      state: value,
      search: null,
      risk: null,
      owner: null,
      vendor: null,
      category: null,
      sort: 'risk',
      direction: 'desc',
      page: null,
    })

  return (
    <div className="ops-page inbox-page">
      <PageHeader
        title="Inbox"
        description="Resolve invoices that need a decision or are blocked by validation."
      />
      <div className="inbox-summary" aria-label="Inbox summary" tabIndex={0}>
        <InboxSummary
          icon={<InboxIcon size={19} />}
          value={review.data?.summary.in_queue ?? 0}
          label="Needs decision"
        />
        <InboxSummary
          icon={<AlertCircle size={19} />}
          value={blocked.data?.summary.open_exceptions ?? 0}
          label="Blocking issues"
          tone="danger"
        />
        <InboxSummary
          icon={<CalendarDays size={19} />}
          value={review.data?.summary.invoice_due_today ?? 0}
          label="Due today"
          tone="warning"
        />
      </div>
      <Panel className="inbox-worklist">
        <div className="inbox-tabs" role="tablist" aria-label="Inbox state">
          {(['needs-decision', 'blocked'] as const).map((item) => (
            <button
              key={item}
              role="tab"
              aria-selected={state === item}
              className={state === item ? 'is-active' : ''}
              onClick={() => selectState(item)}
              onFocus={(event) =>
                event.currentTarget.scrollIntoView({ block: 'nearest', inline: 'center' })
              }
            >
              {item === 'needs-decision' ? 'Needs decision' : 'Blocked'}{' '}
              <span>
                {item === 'needs-decision' ? (review.data?.total ?? 0) : (blocked.data?.total ?? 0)}
              </span>
            </button>
          ))}
        </div>
        <div className="inbox-toolbar">
          <SearchField
            value={search}
            onChange={(value) => setFilter({ search: value || null })}
            placeholder={state === 'blocked' ? 'Search blocked invoices' : 'Search invoices'}
            label="Search inbox"
          />
          <select
            aria-label="Risk"
            value={risk}
            onChange={(event) => setFilter({ risk: event.target.value || null })}
          >
            <option value="">All risk</option>
            <option value="high">High risk</option>
            <option value="medium">Medium risk</option>
            {state === 'needs-decision' ? <option value="low">Low risk</option> : null}
          </select>
          {state === 'blocked' ? (
            <select
              aria-label="Issue type"
              value={category}
              onChange={(event) => setFilter({ category: event.target.value || null })}
            >
              <option value="">All issue types</option>
              {Object.entries(categoryLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="ops-filter-input"
              aria-label="Vendor"
              value={vendor}
              onChange={(event) => setFilter({ vendor: event.target.value || null })}
              placeholder="Vendor"
            />
          )}
          <input
            className="ops-filter-input"
            aria-label="Owner"
            value={owner}
            onChange={(event) => setFilter({ owner: event.target.value || null })}
            placeholder="Owner"
          />
          <select
            aria-label="Sort inbox"
            value={`${sort}:${direction}`}
            onChange={(event) => {
              const [nextSort, nextDirection] = event.target.value.split(':')
              setFilter({ sort: nextSort, direction: nextDirection })
            }}
          >
            <option value="risk:desc">Highest risk</option>
            <option value="updated:asc">Oldest waiting</option>
          </select>
        </div>
        {current.error ? (
          <ErrorState
            message={
              state === 'blocked'
                ? 'Blocked invoices could not be loaded.'
                : 'Invoices awaiting a decision could not be loaded.'
            }
            retry={() => void current.refetch()}
          />
        ) : current.isLoading ? (
          <SkeletonRows count={8} />
        ) : state === 'blocked' ? (
          <BlockedTable items={blocked.data?.items ?? []} />
        ) : (
          <DecisionTable items={review.data?.items ?? []} />
        )}
        {current.data ? (
          <InboxPagination
            page={current.data.page}
            pages={current.data.total_pages}
            total={current.data.total}
            setPage={(value) => setFilter({ page: String(value) })}
          />
        ) : null}
      </Panel>
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
  setter(next)
}
