export type SystemStatus = 'operational' | 'degraded' | 'unavailable' | 'unknown'

export type SystemService = {
  id: string
  name: string
  provider: string | null
  status: SystemStatus
  uptime: number | null
  uptime_label: string
  observed_at: string | null
  activity: string
  evidence: string
  affected_capability: string | null
  unaffected_capability: string | null
}

export type SystemAlert = {
  id: string
  kind: 'service' | 'job'
  target_id: string
  severity: 'critical' | 'warning'
  title: string
  detail: string
}

export type SystemFlowStage = {
  id: string
  label: string
  count: number
  previous_count: number | null
  conversion_percent: number | null
}

export type SystemJob = {
  id: string
  document_id: string
  invoice: string
  filename: string
  stage: string
  status: 'queued' | 'running' | 'retrying' | 'succeeded' | 'failed' | 'dead_letter' | 'cancelled'
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  attempt_count: number
  retryable: boolean
  failure_summary: string | null
}

export type SystemIntegration = {
  id: string
  name: string
  provider: string | null
  status: SystemStatus
  observed_at: string | null
  evidence: string
}

export type SystemAudit = {
  id: string
  timestamp: string
  actor: string
  action: string
  target: string
  result: string
}

export type SystemDashboard = {
  observed_at: string
  freshness: { state: string; label: string }
  overall: { status: SystemStatus; title: string; detail: string }
  kpis: {
    processing_now: number
    waiting: number
    completed_today: number
    needs_attention: number
  }
  services: SystemService[]
  alerts: SystemAlert[]
  flow: {
    window_label: string
    denominator: string
    stages: SystemFlowStage[]
  }
  recent_jobs: SystemJob[]
  integrations: SystemIntegration[]
  audit: SystemAudit[]
  maintenance: { scheduled: boolean; title: string; detail: string }
}
