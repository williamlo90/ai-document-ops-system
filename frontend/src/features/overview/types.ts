export type OverviewTone = 'blue' | 'red' | 'orange' | 'teal' | 'purple'

export type OverviewKpi = {
  id: string
  label: string
  count: number
  note: string
  tone: OverviewTone
  href: string
}

export type OverviewFinding = {
  id: string
  label: string
  count: number
  tone: OverviewTone
  href: string
}

export type OverviewAlert = {
  id: string
  title: string
  detail: string
  severity: 'critical' | 'warning' | 'info'
  href: string
}

export type OverviewQueueItem = {
  document_id: string
  invoice_number: string
  vendor_name: string
  total: string | null
  currency: string | null
  finding: string
  risk: 'high' | 'medium' | 'low'
  confidence: number | null
  due_date: string | null
  owner: string
  recommended_action: 'request_correction' | 'review'
  href: string
}

export type OverviewDashboard = {
  observed_at: string
  actor: { name: string; role: string }
  briefing: {
    attention_count: number
    title: string
    detail: string
    action_label: string
    action_href: string
  }
  kpis: OverviewKpi[]
  findings: OverviewFinding[]
  alerts: OverviewAlert[]
  queue: { total: number; items: OverviewQueueItem[] }
  throughput: {
    window_label: string
    series: Array<{ id: 'processed' | 'sent_for_review'; label: string }>
    points: Array<{ date: string; label: string; processed: number; sent_for_review: number }>
    method: string
  }
  exception_breakdown: {
    total: number
    categories: Array<{
      id: string
      label: string
      count: number
      percentage: number
      color: string
      href: string
    }>
  }
  pipeline: {
    items: Array<{ id: string; label: string; count: number; href: string }>
    excluded_count: number
    note: string
  }
  recent_decisions: Array<{
    id: string
    document_id: string
    title: string
    invoice: string
    vendor: string
    actor: string
    occurred_at: string
    tone: 'success' | 'danger' | 'info' | 'warning'
    href: string
  }>
  capabilities: {
    export_access: boolean
    due_policy: boolean
    sla_policy: boolean
    historical_issue_snapshots: boolean
  }
}
