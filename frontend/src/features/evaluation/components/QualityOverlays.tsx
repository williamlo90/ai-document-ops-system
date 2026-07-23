import type { ReactNode } from 'react'
import { AlertCircle, Check, Info, LoaderCircle, Play, X } from 'lucide-react'
import { Button, StatusBadge } from '../../../shared/ui'
import { cost, delta, percent } from '../format'
import type {
  EvaluationDashboard,
  EvaluationField,
  EvaluationRun,
  ScenarioCoverageGroup,
} from '../types'
import { FieldStatus } from './QualityAnalysis'

export function RunConfirmation({
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

export function FieldDrawer({
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

export function ScenarioDrawer({
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

export function LimitsModal({ run, close }: { run: EvaluationRun; close: () => void }) {
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
