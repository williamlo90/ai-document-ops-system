import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  CheckCircle2,
  FlaskConical,
  Info,
  LoaderCircle,
  Play,
  X,
} from 'lucide-react'
import { api } from '../api/client'
import type {
  EvaluationDashboard,
  EvaluationField,
  EvaluationRun,
  ScenarioCoverageGroup,
} from '../features/evaluation/types'
import { formatDate } from '../features/invoices/format'
import { Button, EmptyState, ErrorState, Panel, SkeletonRows, StatusBadge } from '../shared/ui'

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
  const setRun = (id: string) => updateParams(params, setParams, { run: id || null })
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

function QualitySummary({ run }: { run: EvaluationRun }) {
  return (
    <Panel className="quality-summary" ariaLabel="Selected quality run summary">
      <div>
        <small>Result</small>
        <strong className={run.passed ? 'is-positive' : 'is-negative'}>
          {run.verdict_available ? (run.passed ? 'Passed' : 'Below gate') : 'Not scored'}
        </strong>
      </div>
      <div>
        <small>Field match</small>
        <strong>{percent(run.field_match)}</strong>
        <span>
          {run.fields_matched}/{run.fields_total} labeled fields
        </span>
      </div>
      <div>
        <small>Validation match</small>
        <strong>{percent(run.validation_match)}</strong>
        <span>{run.documents} test documents</span>
      </div>
    </Panel>
  )
}

function FieldPerformance({
  fields,
  open,
}: {
  fields: EvaluationField[]
  open: (field: EvaluationField) => void
}) {
  return (
    <Panel className="evaluation-table-panel" ariaLabel="Field performance">
      <header>
        <div>
          <h2>Field performance</h2>
          <p>Exact match by labeled field</p>
        </div>
      </header>
      {fields.length ? (
        <div className="ops-table-wrap">
          <table className="ops-table evaluation-field-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Current</th>
                <th>Previous</th>
                <th>Delta</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => (
                <tr
                  key={field.field}
                  tabIndex={0}
                  onClick={() => open(field)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') open(field)
                  }}
                >
                  <td>{field.label}</td>
                  <td>{percent(field.current)}</td>
                  <td>{percent(field.previous)}</td>
                  <td
                    className={
                      field.delta_pp != null && field.delta_pp < 0
                        ? 'is-negative'
                        : field.delta_pp != null && field.delta_pp > 0
                          ? 'is-positive'
                          : ''
                    }
                  >
                    {delta(field.delta_pp)}
                  </td>
                  <td>
                    <FieldStatus status={field.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No field results"
          body="The selected run did not record field-level results."
        />
      )}
    </Panel>
  )
}

function FieldStatus({ status }: { status: EvaluationField['status'] }) {
  const tone =
    status === 'improved'
      ? 'success'
      : status === 'regressed'
        ? 'danger'
        : status === 'stable'
          ? 'neutral'
          : 'info'
  return <StatusBadge tone={tone}>{status === 'new' ? 'New baseline' : status}</StatusBadge>
}

function ScenarioCoverage({
  data,
  open,
}: {
  data: EvaluationDashboard['scenario_coverage']
  open: (scenario: ScenarioCoverageGroup) => void
}) {
  return (
    <Panel className="evaluation-coverage-panel" ariaLabel="Scenario coverage">
      <header>
        <div>
          <h2>Scenario coverage</h2>
          <p>Case count versus suite target, not accuracy</p>
        </div>
      </header>
      <div>
        {data.groups.map((group) => (
          <button key={group.id} onClick={() => open(group)}>
            <span>
              <strong>{group.label}</strong>
              <small>
                {group.current} current / {group.target} target
              </small>
            </span>
            <span className="evaluation-coverage-track">
              <i style={{ width: `${(group.coverage ?? 0) * 100}%` }} />
            </span>
            <b>{percent(group.coverage)}</b>
          </button>
        ))}
      </div>
      <footer>{data.claim_boundary}</footer>
    </Panel>
  )
}

function CurrentRun({ run }: { run: EvaluationRun }) {
  return (
    <Panel className="evaluation-current" ariaLabel="Current evaluation run">
      <header>
        <h2>Selected run</h2>
        <StatusBadge tone={run.passed ? 'success' : 'danger'}>
          {run.verdict_available ? (run.passed ? 'Passed' : 'Below gate') : 'Unscored'}
        </StatusBadge>
      </header>
      <dl>
        <div>
          <dt>Completed</dt>
          <dd>{formatDate(run.observed_at, true)}</dd>
        </div>
        <div>
          <dt>Dataset</dt>
          <dd>
            {run.dataset_id} - {run.split}
          </dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{duration(run.duration_seconds)}</dd>
        </div>
        <div>
          <dt>Provider calls</dt>
          <dd>{run.provider_calls ?? 'Not recorded'}</dd>
        </div>
        <div>
          <dt>Provider errors</dt>
          <dd>{run.provider_errors}</dd>
        </div>
        <div>
          <dt>Estimated cost</dt>
          <dd>{cost(run.estimated_cost_usd)}</dd>
        </div>
      </dl>
    </Panel>
  )
}

function KnownLimits({ run, open }: { run: EvaluationRun; open: () => void }) {
  return (
    <Panel className="evaluation-limits" ariaLabel="Known limits">
      <header>
        <AlertTriangle size={17} />
        <h2>Known limits</h2>
      </header>
      <ul>
        {run.limitations.slice(0, 3).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      {run.limitations.length > 3 ? (
        <button className="ops-link" onClick={open}>
          Read all limits
        </button>
      ) : null}
    </Panel>
  )
}

function RecentRuns({
  runs,
  selectedId,
  attempts,
  selectRun,
}: {
  runs: EvaluationDashboard['runs']
  selectedId: string
  attempts: EvaluationDashboard['attempts']
  selectRun: (id: string) => void
}) {
  return (
    <Panel className="evaluation-recent" ariaLabel="Recent evaluation runs">
      <header>
        <h2>Recent runs</h2>
      </header>
      <div>
        {runs.slice(0, 4).map((run) => (
          <button
            key={run.id}
            className={run.id === selectedId ? 'is-selected' : ''}
            onClick={() => selectRun(run.id)}
          >
            <span>
              <strong>{shortDate(run.observed_at)}</strong>
              <small>
                {run.dataset_id} - {run.split}
              </small>
            </span>
            <StatusBadge
              tone={!run.verdict_available ? 'neutral' : run.passed ? 'success' : 'danger'}
            >
              {!run.verdict_available ? 'Unscored' : run.passed ? 'Passed' : 'Below gate'}
            </StatusBadge>
          </button>
        ))}
      </div>
      {attempts.some((attempt) => attempt.status === 'failed') ? (
        <section>
          <h3>Failed attempts</h3>
          {attempts
            .filter((attempt) => attempt.status === 'failed')
            .slice(0, 2)
            .map((attempt) => (
              <p key={attempt.id}>
                <AlertCircle size={14} />
                <span>
                  {formatDate(attempt.started_at, true)}
                  <small>
                    {attempt.documents_processed}/{attempt.documents_requested} documents; no
                    partial result promoted.
                  </small>
                </span>
              </p>
            ))}
        </section>
      ) : null}
    </Panel>
  )
}

function RunConfirmation({
  preflight,
  pending,
  error,
  close,
  confirm,
}: {
  preflight: EvaluationDashboard['preflight']
  pending: boolean
  error: Error | null
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
        className="ops-modal evaluation-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-evaluation-title"
      >
        <header>
          <div>
            <h2 id="run-evaluation-title">Run evaluation?</h2>
            <p>This starts real calls to the configured document providers.</p>
          </div>
          <button
            className="ops-icon-button"
            aria-label="Close evaluation confirmation"
            disabled={pending}
            onClick={close}
          >
            <X size={19} />
          </button>
        </header>
        <dl>
          <div>
            <dt>Test set</dt>
            <dd>
              {preflight.dataset_label} - v{preflight.dataset_version}
            </dd>
          </div>
          <div>
            <dt>Documents</dt>
            <dd>
              {preflight.documents} of {preflight.available_documents}
              {preflight.limited ? ' (safety cap)' : ''}
            </dd>
          </div>
          <div>
            <dt>Estimated provider calls</dt>
            <dd>{preflight.provider_calls_estimate}</dd>
          </div>
          <div>
            <dt>Estimated cost</dt>
            <dd>
              {preflight.estimated_cost_usd == null
                ? 'Calculated after completion'
                : cost(preflight.estimated_cost_usd)}
            </dd>
          </div>
          <div>
            <dt>Provider</dt>
            <dd>{preflight.provider}</dd>
          </div>
        </dl>
        <p>
          <Info size={16} />
          {preflight.cost_note}
        </p>
        {pending ? (
          <div className="evaluation-running" role="status">
            <LoaderCircle className="spin" size={20} />
            <span>
              <strong>Running evaluation</strong>
              <small>Waiting for observed provider results. No simulated progress is shown.</small>
            </span>
          </div>
        ) : null}
        {error ? (
          <div className="evaluation-run-error" role="alert">
            <AlertCircle size={17} />
            <span>
              <strong>Evaluation could not be completed</strong>
              <small>{error.message} No partial result replaced the latest valid run.</small>
            </span>
          </div>
        ) : null}
        <footer>
          <Button disabled={pending} onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" disabled={pending} onClick={confirm}>
            {pending ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}{' '}
            {pending ? 'Running...' : 'Run evaluation'}
          </Button>
        </footer>
      </section>
    </div>
  )
}

function FieldDrawer({
  field,
  tolerance,
  close,
}: {
  field: EvaluationField
  tolerance: number
  close: () => void
}) {
  return (
    <Drawer title={field.label} eyebrow="Field performance" close={close}>
      <div className="evaluation-drawer-verdict">
        <FieldStatus status={field.status} />
        <strong>{percent(field.current)}</strong>
        <span>{delta(field.delta_pp)}</span>
      </div>
      <dl>
        <div>
          <dt>Current matched cases</dt>
          <dd>
            {field.current_matches ?? '-'} / {field.current_denominator}
          </dd>
        </div>
        <div>
          <dt>Previous matched cases</dt>
          <dd>
            {field.previous_matches ?? '-'} / {field.previous_denominator ?? '-'}
          </dd>
        </div>
        <div>
          <dt>Regression tolerance</dt>
          <dd>+/-{tolerance.toFixed(1)} pp</dd>
        </div>
      </dl>
      <section>
        <h3>Interpretation</h3>
        <p>
          {field.previous == null
            ? 'This run has no retained comparable per-field baseline, so the value is not labeled improved or regressed.'
            : field.status === 'stable'
              ? 'The observed change remains inside the configured regression tolerance.'
              : `The change exceeds the configured ${tolerance.toFixed(1)} pp tolerance.`}
        </p>
        <p>Case-level expected and predicted values are not exposed by this sanitized aggregate.</p>
      </section>
    </Drawer>
  )
}

function ScenarioDrawer({
  scenario,
  claim,
  close,
}: {
  scenario: ScenarioCoverageGroup
  claim: string
  close: () => void
}) {
  return (
    <Drawer title={scenario.label} eyebrow="Scenario coverage" close={close}>
      <div className="evaluation-drawer-verdict">
        <StatusBadge tone={scenario.remaining ? 'warning' : 'success'}>
          {scenario.remaining ? `${scenario.remaining} case gap` : 'Target met'}
        </StatusBadge>
        <strong>
          {scenario.current}/{scenario.target}
        </strong>
        <span>{percent(scenario.coverage)}</span>
      </div>
      <section>
        <h3>Included cases</h3>
        <ul className="evaluation-case-list">
          {scenario.case_ids.map((item) => (
            <li key={item}>
              <Check size={14} />
              {item.replaceAll('_', ' ')}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3>Claim boundary</h3>
        <p>{claim}</p>
      </section>
    </Drawer>
  )
}

function Drawer({
  title,
  eyebrow,
  close,
  children,
}: {
  title: string
  eyebrow: string
  close: () => void
  children: ReactNode
}) {
  return (
    <div
      className="ops-modal-backdrop evaluation-drawer-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <aside
        className="evaluation-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evaluation-drawer-title"
      >
        <header>
          <div>
            <span>{eyebrow}</span>
            <h2 id="evaluation-drawer-title">{title}</h2>
          </div>
          <button className="ops-icon-button" aria-label="Close details" onClick={close}>
            <X size={19} />
          </button>
        </header>
        {children}
      </aside>
    </div>
  )
}

function LimitsModal({ run, close }: { run: EvaluationRun; close: () => void }) {
  return (
    <div
      className="ops-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <section
        className="ops-modal evaluation-limits-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="limits-title"
      >
        <header>
          <div>
            <h2 id="limits-title">What these results do not prove</h2>
            <p>
              {run.dataset_class} - {run.split}
            </p>
          </div>
          <button className="ops-icon-button" aria-label="Close limits" onClick={close}>
            <X size={19} />
          </button>
        </header>
        <ul>
          {run.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <footer>
          <Button variant="primary" onClick={close}>
            Done
          </Button>
        </footer>
      </section>
    </div>
  )
}

function EvaluationSkeleton() {
  return (
    <div className="evaluation-skeleton">
      <Panel>
        <SkeletonRows count={2} />
      </Panel>
      <div className="evaluation-main-grid">
        <Panel>
          <SkeletonRows count={8} />
        </Panel>
        <Panel>
          <SkeletonRows count={7} />
        </Panel>
      </div>
    </div>
  )
}

function percent(value: number | null | undefined) {
  return value == null ? '-' : `${(value * 100).toFixed((value * 100) % 1 ? 1 : 0)}%`
}

function duration(seconds: number | null) {
  if (seconds == null) return 'Not recorded'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

function cost(value: number | null) {
  return value == null ? 'Not recorded' : `$${value.toFixed(value < 0.1 ? 4 : 2)}`
}

function delta(value: number | null) {
  if (value == null) return '-'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} pp`
}

function shortDate(value: string | null) {
  if (!value) return 'Unknown date'
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(
    new Date(value),
  )
}

function updateParams(
  current: URLSearchParams,
  setter: ReturnType<typeof useSearchParams>[1],
  values: Record<string, string | null>,
) {
  const next = new URLSearchParams(current)
  Object.entries(values).forEach(([key, value]) =>
    value ? next.set(key, value) : next.delete(key),
  )
  setter(next)
}
