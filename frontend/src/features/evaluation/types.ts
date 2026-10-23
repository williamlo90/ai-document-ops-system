export type EvaluationGate = {
  field_match: number
  validation_match: number
  regression_tolerance_pp: number
}

export type EvaluationPreflight = {
  dataset_id: string
  dataset_version: string
  dataset_label: string
  available_documents: number
  documents: number
  limited: boolean
  provider_calls_estimate: number
  estimated_cost_usd: number | null
  cost_note: string
  runnable: boolean
  provider: string
}

export type EvaluationRun = {
  id: string
  label: string
  dataset_id: string
  dataset_version: string
  dataset_class: string
  split: string
  provider: string
  source: string
  source_document: string | null
  observed_at: string
  documents: number
  fields_matched: number
  fields_total: number
  field_match: number | null
  validation_match: number | null
  document_exact_match: number | null
  approval_blocker_accuracy: number | null
  provider_errors: number
  duration_seconds: number | null
  duration_kind: 'wall_clock' | 'summed_provider_latency' | 'unavailable'
  provider_calls: number | null
  estimated_cost_usd: number | null
  cost_status: string | null
  cost_claim: string | null
  passed: boolean
  verdict_available: boolean
  by_field: Record<string, number>
  failure_taxonomy: Record<string, number>
  limitations: string[]
  is_current: boolean
}

export type EvaluationSelectorRun = Pick<
  EvaluationRun,
  'id' | 'label' | 'dataset_id' | 'split' | 'observed_at' | 'passed' | 'verdict_available'
> & { current: boolean }

export type EvaluationTrendPoint = {
  id: string
  observed_at: string
  field_match: number | null
  validation_match: number | null
  documents: number
  provider_errors: number
  estimated_cost_usd: number | null
  selected: boolean
}

export type EvaluationRegression = {
  comparison_run_id: string | null
  comparison_observed_at: string | null
  tolerance_pp: number
  comparable_fields: number
  improved: number
  stable: number
  regressed: number
  new_fields: number
  excluded_fields: number
  new_failures: number | null
}

export type EvaluationField = {
  field: string
  label: string
  current: number | null
  previous: number | null
  delta_pp: number | null
  status: 'improved' | 'stable' | 'regressed' | 'new' | 'excluded'
  current_matches: number | null
  current_denominator: number
  previous_matches: number | null
  previous_denominator: number | null
}

export type ScenarioCoverageGroup = {
  id: string
  label: string
  current: number
  target: number
  coverage: number | null
  remaining: number
  case_ids: string[]
}

export type EvaluationAttempt = {
  id: string
  status: 'running' | 'succeeded' | 'failed'
  dataset_id: string
  dataset_version: string
  documents_requested: number
  documents_processed: number
  provider_calls: number
  run_id: string | null
  error_code: string | null
  error_message: string | null
  requested_by: string
  started_at: string
  completed_at: string | null
}

export type EvaluationDashboard = {
  gates: EvaluationGate
  preflight: EvaluationPreflight
  runs: EvaluationSelectorRun[]
  selected_run: EvaluationRun | null
  trend: EvaluationTrendPoint[]
  regression: EvaluationRegression | null
  fields: EvaluationField[]
  scenario_coverage: {
    dataset_id: string
    dataset_version: string
    claim_boundary: string
    included_in_selected_run: boolean
    groups: ScenarioCoverageGroup[]
  }
  attempts: EvaluationAttempt[]
}
