import { EmptyState, Panel, StatusBadge } from '../../../shared/ui'
import { delta, percent } from '../format'
import type {
  EvaluationDashboard,
  EvaluationField,
  EvaluationRun,
  ScenarioCoverageGroup,
} from '../types'

export function QualitySummary({ run }: { run: EvaluationRun }) {
  return (
    <Panel className="quality-summary" ariaLabel="Selected quality run summary">
      <div>
        <small>Header / validation gate</small>
        <strong className={run.passed ? 'is-positive' : 'is-negative'}>
          {run.verdict_available ? (run.passed ? 'Passed' : 'Below gate') : 'Not scored'}
        </strong>
      </div>
      <div>
        <small>Header field match</small>
        <strong>{percent(run.field_match)}</strong>
        <span>
          {run.fields_matched}/{run.fields_total} labeled header fields
        </span>
      </div>
      <div>
        <small>Validation match</small>
        <strong>{percent(run.validation_match)}</strong>
        <span>{run.documents} test documents</span>
      </div>
      <div>
        <small>Full-invoice exact match</small>
        <strong>
          {run.full_invoice_exact_match == null ? 'N/A' : percent(run.full_invoice_exact_match)}
        </strong>
        <span>
          {run.full_invoice_documents_total
            ? `${run.full_invoice_documents_matched}/${run.full_invoice_documents_total} fully labeled invoices (${run.documents} total)`
            : 'Not measured: complete header, line and source labels required'}
        </span>
        <span>Includes required source evidence</span>
      </div>
      <div>
        <small>Line-item field match</small>
        <strong>{run.line_field_match == null ? 'N/A' : percent(run.line_field_match)}</strong>
        <span>
          {run.missing_lines ?? 0} missing / {run.extra_lines ?? 0} extra lines
        </span>
        <span>
          {run.ambiguous_line_groups ?? 0} ambiguous groups. Exact-line precision{' '}
          {percent(run.line_precision)} / recall {percent(run.line_recall)}
        </span>
      </div>
      <div>
        <small>Processing completed</small>
        <strong>
          {run.processing_completion == null ? 'N/A' : percent(run.processing_completion)}
        </strong>
        <span>
          Validation completed:{' '}
          {run.validation_completion == null ? 'N/A' : percent(run.validation_completion)}
        </span>
        <span>
          {run.evaluation_input === 'original_provider_extraction'
            ? 'Original extraction, before reviewer corrections'
            : 'Legacy or supplied results; extraction stage not recorded'}
        </span>
      </div>
    </Panel>
  )
}

export function FieldPerformance({
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
          <p>Exact match by labeled header field</p>
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

export function FieldStatus({ status }: { status: EvaluationField['status'] }) {
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

export function ScenarioCoverage({
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
