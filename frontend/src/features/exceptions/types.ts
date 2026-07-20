export type ExceptionRisk = 'high' | 'medium'
export type ExceptionCategory = 'vendor_invoice' | 'tax_amount' | 'duplicate' | 'dates_details' | 'other'

export type ExceptionItem = {
  id: string
  document_id: string
  work_item_id: string | null
  original_filename: string
  invoice_number: string | null
  vendor_name: string | null
  total: string | null
  currency: string | null
  issue: string
  category: ExceptionCategory
  risk: ExceptionRisk
  blocks_approval: boolean
  owner: string | null
  detected_at: string
  age_seconds: number
}

export type ExceptionDetail = ExceptionItem & {
  message: string
  code: string
  field_name: string
  field_value: string | null
  required_action: string
  related_checks: Array<{ label: string; status: 'passed' | 'warning' | 'blocked' }>
}

export type ExceptionListResponse = {
  items: ExceptionItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
  summary: {
    open_exceptions: number
    high_risk: number
    warning_issues: number
    invoices_affected: number
    categories: Partial<Record<ExceptionCategory, number>>
    top_issues: Array<{ label: string; category: ExceptionCategory; count: number }>
  }
  assignee_options: string[]
  capabilities: {
    resolved_history: boolean
    due_policy: boolean
    validated_resolution_only: boolean
  }
}

export type ExceptionDetailResponse = { exception: ExceptionDetail }
export type ExceptionAssignmentResponse = {
  exception: ExceptionDetail
  assignment: { work_item_id: string; assignee: string | null; recorded_by: string; recorded_at: string }
}
