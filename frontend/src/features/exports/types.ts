export type ExportMetric = { count: number; amount: string | null; currency: string | null }

export type ExportInvoiceItem = {
  id: string
  invoice_label: string
  filename: string
  vendor_name: string | null
  approved_by: string | null
  approved_at: string | null
  total: string | null
  currency: string | null
  status: 'ready' | 'in_batch' | 'exported' | 'blocked' | 'drafts'
  issue: string | null
  batch_id: string | null
  updated_at: string
}

export type ExportCheck = {
  code: string
  label: string
  state: 'passed' | 'failed' | 'warning'
  detail: string
}

export type ExportBatch = {
  id: string
  name: string | null
  status: 'draft' | 'ready' | 'running' | 'completed' | 'failed'
  destination: string
  destination_label: string
  format: string
  created_by: string
  invoice_count: number
  total_amount: string | null
  currency: string | null
  invoices: ExportInvoiceItem[]
  eligibility: ExportCheck[]
  last_run_id: string | null
  created_at: string
  updated_at: string
}

export type ExportRun = {
  id: string
  batch_id: string
  status: 'running' | 'succeeded' | 'failed'
  destination: string
  destination_label: string
  format: string
  actor: string
  invoice_count: number
  total_amount: string | null
  currency: string | null
  attempt_count: number
  file_name: string | null
  download_available: boolean
  error_code: string | null
  error_message: string | null
  retryable: boolean
  created_at: string
  completed_at: string | null
  stages?: Array<{ label: string; status: 'completed' | 'failed' | 'not_started' | 'running' }>
}

export type ExportWorkspaceResponse = {
  capabilities: {
    destinations: Array<{ id: string; label: string; formats: string[]; mode: string }>
    scheduling: boolean
    drafts: boolean
    retry: boolean
    configured_provider: string
    destination_available: boolean
  }
  summary: {
    ready: ExportMetric
    in_batch: ExportMetric
    exported: ExportMetric
    blocked: ExportMetric
  }
  items: ExportInvoiceItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
  filters: { vendors: string[]; currencies: string[]; approvers: string[] }
  batch: ExportBatch | null
  recent_runs: ExportRun[]
}

export type ExportBatchMutationResponse = {
  batch: ExportBatch
  accepted: string[]
  rejected: Array<{ document_id: string; reason: string }>
}
