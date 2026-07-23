import { AlertCircle, AlertTriangle } from 'lucide-react'
import { formatDate } from '../../invoices/format'
import { Panel, StatusBadge } from '../../../shared/ui'
import { cost, duration, shortDate } from '../format'
import type { EvaluationDashboard, EvaluationRun } from '../types'

export function CurrentRun({ run }: { run: EvaluationRun }) {
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

export function KnownLimits({ run, open }: { run: EvaluationRun; open: () => void }) {
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

export function RecentRuns({
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
