export type ReviewQueueItem = {
  id: string
  original_filename: string
  invoice_number: string | null
  vendor_name: string | null
  total: string | null
  currency: string | null
  invoice_date: string | null
  due_date: string | null
  owner: string
  risk: 'high' | 'medium' | 'low'
  confidence: number | null
  finding: string | null
  blocker_count: number
  issue_count: number
  can_approve: boolean
  recommended_action: 'request_correction' | 'review'
  age_seconds: number
  created_at: string
  updated_at: string
}

export type ReviewWorklist = {
  items: ReviewQueueItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
  summary: { in_queue: number; high_risk: number; invoice_due_today: number; average_review_seconds: number | null }
}

export type ReviewWorkflow = {
  current_stage: string
  current_owner: string
  waiting_for: string
  next_action: string
  attention_reason: string | null
  work_item: { business_context?: Record<string, string>; assignee?: string } | null
}

export type DecisionResult = {
  document: { id: string; status: string; updated_at: string }
  review_task: { status: string; reviewer_notes: string; reviewed_by: string | null; reviewed_at: string | null }
  decision: {
    status: string
    actor: string | null
    recorded_at: string | null
    note: string
    audit_event_count: number
    export_eligibility: string
  }
}
