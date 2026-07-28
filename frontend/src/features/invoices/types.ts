export type InvoiceItem = {
  id: string
  original_filename: string
  submitted_by: string
  status: string
  business_status: string
  current_stage: string
  current_owner: string
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  total: string | null
  currency: string | null
  created_at: string
  updated_at: string
  validation_issue_count: number
  validation_error_count: number
  validation_codes: string[]
  has_validation_errors: boolean
  export_state: 'eligible' | 'exported' | 'not_eligible'
  work_item_id: string | null
  correction_reason: string | null
}

export type InvoiceListResponse = {
  items: InvoiceItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
  summary: {
    all: number
    waiting_review: number
    needs_correction: number
    approved: number
    exported: number
  }
  insights: { flagged: number; duplicates_suspected: number; tax_amount_issues: number }
}

export type InvoiceExtraction = {
  data: {
    vendor_name?: string | null
    invoice_number?: string | null
    invoice_date?: string | null
    due_date?: string | null
    subtotal?: string | null
    tax?: string | null
    total?: string | null
    currency?: string | null
    line_items?: Array<Record<string, string | null>>
  }
  validation: Array<{ field_name: string; severity: string; code: string; message: string }>
  confidence: Array<{
    field_name: string
    score: number | null
    source_page?: number | null
    source_text?: string | null
  }>
}

export type InvoiceDetailResponse = {
  document: InvoiceItem
  extraction: InvoiceExtraction | null
  correction_summary?: {
    latest_change_count: number
    latest_changed_fields: string[]
    latest_changes: Array<{
      field_path: string
      original_ai_value: string | number | boolean | null
      before_value: string | number | boolean | null
      after_value: string | number | boolean | null
    }>
    latest_actor: string
    latest_reason: string
  } | null
  audit_events: Array<{
    id: string
    event_type: string
    actor: string
    old_status?: string | null
    new_status?: string | null
    payload_summary?: string | null
    created_at: string
  }>
}
