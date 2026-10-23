import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { CheckCircle2, FlaskConical, Info, LoaderCircle, Play, X } from 'lucide-react'
import { api } from '../api/client'
import { EvaluationSkeleton } from '../features/evaluation/components/EvaluationSkeleton'
import {
  FieldPerformance,
  QualitySummary,
  ScenarioCoverage,
} from '../features/evaluation/components/QualityAnalysis'
import {
  CurrentRun,
  KnownLimits,
  RecentRuns,
} from '../features/evaluation/components/QualitySidebar'
import {
  FieldDrawer,
  LimitsModal,
  RunConfirmation,
  ScenarioDrawer,
} from '../features/evaluation/components/QualityOverlays'
import { percent, shortDate } from '../features/evaluation/format'
import type {
  EvaluationDashboard,
  EvaluationField,
  ScenarioCoverageGroup,
} from '../features/evaluation/types'
import { updateSearchParams } from '../shared/searchParams'
import { Button, EmptyState, ErrorState } from '../shared/ui'

export function EvaluationPage() {
  const [params, setParams] = useSearchParams()
  const queryClient = useQueryClient()
  const runId = params.get('run')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [selectedField, setSelectedField] = useState<EvaluationField | null>(null)
  const [selectedScenario, setSelectedScenario] = useState<ScenarioCoverageGroup | null>(null)
  const [limitsOpen, setLimitsOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 4500)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const dashboard = useQuery({
    queryKey: ['evaluation-dashboard', runId],
    queryFn: () =>
      api<EvaluationDashboard>(
        `/evaluation/dashboard?range_limit=10${runId ? `&run=${encodeURIComponent(runId)}` : ''}`,
      ),
  })
  const runEvaluation = useMutation({
    mutationFn: () => api<{ run_id: string }>('/evaluation/runs', { method: 'POST' }),
    onSuccess: (result) => {
      setConfirmOpen(false)
      setRun(result.run_id)
      setToast('Evaluation completed and added to comparison history.')
      void queryClient.invalidateQueries({ queryKey: ['evaluation-dashboard'] })
    },
  })
  const setRun = (id: string) => updateSearchParams(params, setParams, { run: id || null })
  const selected = dashboard.data?.selected_run

  return (
    <div className="ops-page evaluation-page">
      <header className="evaluation-header">
        <div>
          <div className="evaluation-title-row">
            <h1>Quality</h1>
            <span
              className="evaluation-synthetic-badge"
              title="Results are based on labeled synthetic documents and do not represent production accuracy."
            >
              <FlaskConical size={15} /> Synthetic test set
            </span>
          </div>
          <p>Check extraction and validation results against labeled invoice cases.</p>
        </div>
        <div className="evaluation-header-actions">
          <label>
            <span className="sr-only">Selected evaluation run</span>
            <select
              value={selected?.id ?? ''}
              onChange={(event) => setRun(event.target.value)}
              disabled={!dashboard.data?.runs.length}
            >
              {dashboard.data?.runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {shortDate(run.observed_at)} - {run.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="primary"
            disabled={!dashboard.data?.preflight.runnable || runEvaluation.isPending}
            onClick={() => {
              runEvaluation.reset()
              setConfirmOpen(true)
            }}
          >
            {runEvaluation.isPending ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Play size={17} />
            )}{' '}
            {runEvaluation.isPending ? 'Running evaluation...' : 'Run evaluation'}
          </Button>
        </div>
      </header>
      {dashboard.isLoading ? (
        <EvaluationSkeleton />
      ) : dashboard.error ? (
        <ErrorState
          message={(dashboard.error as Error).message}
          retry={() => void dashboard.refetch()}
        />
      ) : !selected || !dashboard.data ? (
        <EmptyState
          title="No evaluation runs yet"
          body="Run the synthetic test set to establish the first quality baseline."
          action={
            <Button variant="primary" onClick={() => setConfirmOpen(true)}>
              Run first evaluation
            </Button>
          }
        />
      ) : (
        <>
          <QualitySummary run={selected} />
          <div className="evaluation-main-grid">
            <div className="evaluation-analysis">
              <div className="evaluation-detail-grid">
                <FieldPerformance fields={dashboard.data.fields} open={setSelectedField} />
                <ScenarioCoverage
                  data={dashboard.data.scenario_coverage}
                  open={setSelectedScenario}
                />
              </div>
              <div className="evaluation-gate-note">
                <Info size={16} />
                <span>
                  Pass gates: Field match &gt;= {percent(dashboard.data.gates.field_match)} and
                  validation match &gt;= {percent(dashboard.data.gates.validation_match)}. Changes
                  within +/-{dashboard.data.gates.regression_tolerance_pp.toFixed(1)} pp are stable.
                </span>
              </div>
            </div>
            <aside className="evaluation-sidebar">
              <CurrentRun run={selected} />
              <KnownLimits run={selected} open={() => setLimitsOpen(true)} />
              <RecentRuns
                runs={dashboard.data.runs}
                selectedId={selected.id}
                attempts={dashboard.data.attempts}
                selectRun={setRun}
              />
            </aside>
          </div>
        </>
      )}
      {confirmOpen && dashboard.data ? (
        <RunConfirmation
          preflight={dashboard.data.preflight}
          pending={runEvaluation.isPending}
          error={runEvaluation.error as Error | null}
          close={() => {
            if (!runEvaluation.isPending) setConfirmOpen(false)
          }}
          confirm={() => runEvaluation.mutate()}
        />
      ) : null}
      {selectedField ? (
        <FieldDrawer
          field={selectedField}
          tolerance={dashboard.data?.gates.regression_tolerance_pp ?? 0.5}
          close={() => setSelectedField(null)}
        />
      ) : null}
      {selectedScenario ? (
        <ScenarioDrawer
          scenario={selectedScenario}
          claim={dashboard.data?.scenario_coverage.claim_boundary ?? ''}
          close={() => setSelectedScenario(null)}
        />
      ) : null}
      {limitsOpen && selected ? (
        <LimitsModal run={selected} close={() => setLimitsOpen(false)} />
      ) : null}
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
