import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, LoaderCircle, RefreshCw, X } from 'lucide-react'
import { api } from '../api/client'
import {
  AuditDrawer,
  JobDrawer,
  ServiceDrawer,
} from '../features/system/components/OperationsDrawers'
import {
  OperationsSummary,
  OverallBanner,
  SystemTabs,
} from '../features/system/components/OperationsOverview'
import { OperationsSkeleton } from '../features/system/components/OperationsSkeleton'
import {
  AttentionPanel,
  AuditView,
  IntegrationsView,
  ProcessingView,
  StatusView,
} from '../features/system/components/OperationsViews'
import { isSystemTab, type SystemTab } from '../features/system/selectors'
import type {
  SystemAudit,
  SystemDashboard,
  SystemJob,
  SystemService,
} from '../features/system/types'
import { formatDate } from '../shared/format'
import { updateSearchParams } from '../shared/searchParams'
import { Button, ErrorState } from '../shared/ui'

export function SystemPage() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const requestedTab = params.get('tab')
  const tab: SystemTab = isSystemTab(requestedTab) ? requestedTab : 'status'
  const filter = params.get('filter')
  const stage = params.get('stage')
  const [service, setService] = useState<SystemService | null>(null)
  const [job, setJob] = useState<SystemJob | null>(null)
  const [audit, setAudit] = useState<SystemAudit | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const dashboard = useQuery({
    queryKey: ['system-dashboard'],
    queryFn: () => api<SystemDashboard>('/system/dashboard'),
    refetchInterval: 15_000,
  })
  const retry = useMutation({
    mutationFn: (id: string) => api(`/operations/jobs/${id}/retry`, { method: 'POST' }),
    onSuccess: () => {
      setJob(null)
      setToast('Retry accepted. The invoice is waiting to be processed again.')
      void queryClient.invalidateQueries({ queryKey: ['system-dashboard'] })
    },
  })

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 4200)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const setTab = (value: SystemTab, nextFilter?: string | null, nextStage?: string | null) => {
    updateSearchParams(params, setParams, {
      tab: value === 'status' ? null : value,
      filter: nextFilter ?? null,
      stage: nextStage ?? null,
    })
  }
  const refresh = async () => {
    const result = await dashboard.refetch()
    if (!result.error) setToast('Operations status refreshed.')
  }
  const openAlert = (targetId: string, kind: string) => {
    if (kind === 'service')
      setService(dashboard.data?.services.find((item) => item.id === targetId) ?? null)
    else setJob(dashboard.data?.recent_jobs.find((item) => item.id === targetId) ?? null)
  }

  return (
    <div className="ops-page system-page">
      <header className="system-header">
        <div>
          <h1>Operations</h1>
          <p>Find processing failures, retry eligible jobs, and verify service status.</p>
        </div>
        <div>
          <Button disabled={dashboard.isFetching} onClick={() => void refresh()}>
            {dashboard.isFetching ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <RefreshCw size={16} />
            )}{' '}
            {dashboard.isFetching ? 'Refreshing...' : 'Refresh status'}
          </Button>
          <span>
            {dashboard.data
              ? `Observed ${formatDate(dashboard.data.observed_at, true)}`
              : 'Waiting for status'}
          </span>
        </div>
      </header>
      {dashboard.isLoading ? (
        <OperationsSkeleton />
      ) : dashboard.error ? (
        <ErrorState
          message={(dashboard.error as Error).message}
          retry={() => void dashboard.refetch()}
        />
      ) : dashboard.data ? (
        <>
          <OverallBanner
            data={dashboard.data}
            open={() =>
              setService(
                dashboard.data!.services.find((item) => item.status !== 'operational') ??
                  dashboard.data!.services[0],
              )
            }
          />
          <OperationsSummary data={dashboard.data} setTab={setTab} />
          <SystemTabs active={tab} select={setTab} />
          {tab === 'status' ? (
            <div className="system-status-stack">
              <AttentionPanel data={dashboard.data} open={openAlert} />
              <StatusView data={dashboard.data} openService={setService} />
            </div>
          ) : null}
          {tab === 'processing' ? (
            <ProcessingView
              data={dashboard.data}
              filter={filter}
              stage={stage}
              clear={() => setTab('processing')}
              openJob={setJob}
              retry={(item) => retry.mutate(item.id)}
              pending={retry.isPending}
            />
          ) : null}
          {tab === 'integrations' ? (
            <IntegrationsView
              data={dashboard.data.integrations}
              open={(item) =>
                setService(
                  dashboard.data!.services.find((serviceItem) => serviceItem.id === item.id) ??
                    null,
                )
              }
            />
          ) : null}
          {tab === 'audit' ? <AuditView data={dashboard.data.audit} open={setAudit} /> : null}
        </>
      ) : null}
      {service ? <ServiceDrawer service={service} close={() => setService(null)} /> : null}
      {job ? (
        <JobDrawer
          job={job}
          pending={retry.isPending}
          error={retry.error as Error | null}
          close={() => setJob(null)}
          retry={() => retry.mutate(job.id)}
        />
      ) : null}
      {audit ? <AuditDrawer audit={audit} close={() => setAudit(null)} /> : null}
      {toast ? (
        <div className="ops-toast" role="status">
          <CheckCircle2 size={17} />
          {toast}
          <button aria-label="Dismiss message" onClick={() => setToast(null)}>
            <X size={14} />
          </button>
        </div>
      ) : null}
    </div>
  )
}
