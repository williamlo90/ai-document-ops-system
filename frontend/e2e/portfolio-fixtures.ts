import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

import type { EvaluationDashboard } from '../src/features/evaluation/types'
import type {
  ExceptionDetail,
  ExceptionItem,
  ExceptionListResponse,
} from '../src/features/exceptions/types'
import type {
  ExportBatch,
  ExportInvoiceItem,
  ExportRun,
  ExportWorkspaceResponse,
} from '../src/features/exports/types'
import {
  belongsToExportView,
  isExportView,
  type ExportView,
} from '../src/features/exports/selectors'
import { isDecisionQueueItem } from '../src/features/inbox/selectors'
import type {
  InvoiceDetailResponse,
  InvoiceItem,
  InvoiceListResponse,
} from '../src/features/invoices/types'
import {
  belongsToInvoiceLifecycle,
  isInvoiceLifecycleFilter,
} from '../src/features/invoices/selectors'
import type { ReviewQueueItem, ReviewWorklist, ReviewWorkflow } from '../src/features/review/types'
import type { SystemDashboard } from '../src/features/system/types'

export type PortfolioRole = 'administrator' | 'reviewer' | 'uploader'

const observedAt = '2026-07-21T03:15:00Z'
const cleanPdf = readFileSync(
  path.resolve(
    '../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf',
  ),
)
const duplicatePdf = readFileSync(
  path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_copy.pdf'),
)

const invoiceSeeds = [
  [
    'doc-acme',
    'SIP-7788',
    'Summit Industrial Parts',
    '704.00',
    'needs_review',
    'James Smith',
    '2026-08-15',
    'total_mismatch',
  ],
  [
    'doc-northstar',
    'INV-2026-04568',
    'Northstar Office',
    '3275.40',
    'needs_review',
    'Alex Davis',
    '2026-07-20',
    'tax_amount_mismatch',
  ],
  [
    'doc-meridian',
    'INV-2026-04569',
    'Meridian Freight',
    '8600.75',
    'needs_review',
    'Kelly Morgan',
    '2026-07-21',
    'duplicate_invoice',
  ],
  [
    'doc-cobalt-review',
    'INV-2026-04575',
    'Cobalt Facilities',
    '1280.00',
    'needs_review',
    'James Smith',
    '2026-07-23',
    '',
  ],
  [
    'doc-acme-approved',
    'INV-2026-04570',
    'Acme Logistics',
    '6120.00',
    'approved',
    'James Smith',
    '2026-07-21',
    '',
  ],
  [
    'doc-northstar-correction',
    'INV-2026-04571',
    'Northstar Office',
    '1842.10',
    'needs_correction',
    'Alex Davis',
    '2026-07-22',
    'receipt_required',
  ],
  [
    'doc-meridian-correction',
    'INV-2026-04572',
    'Meridian Freight',
    '4950.00',
    'needs_correction',
    'Kelly Morgan',
    '2026-07-22',
    'total_mismatch',
  ],
  [
    'doc-greenline-approved',
    'INV-2026-04573',
    'Greenline Supply',
    '2315.50',
    'approved',
    'James Smith',
    '2026-07-23',
    '',
  ],
  [
    'doc-northstar-exported',
    'INV-2026-04574',
    'Northstar Office',
    '910.25',
    'exported',
    'Alex Davis',
    '2026-07-23',
    '',
  ],
] as const

const findingLabels: Record<string, string> = {
  tax_amount_mismatch: 'Tax amount mismatch',
  duplicate_invoice: 'Possible duplicate',
  receipt_required: 'Receipt required',
  total_mismatch: 'Total does not match',
}

function invoiceFromSeed(seed: (typeof invoiceSeeds)[number]): InvoiceItem {
  const [id, invoiceNumber, vendor, total, status, owner, dueDate, issue] = seed
  const businessStatus = status
  return {
    id,
    original_filename: `${invoiceNumber.toLowerCase()}.pdf`,
    submitted_by: 'invoice-uploader',
    status: status === 'needs_correction' ? 'needs_review' : status,
    business_status: businessStatus,
    current_stage:
      status === 'needs_correction'
        ? 'correction_requested'
        : status === 'needs_review'
          ? 'needs_review'
          : status,
    current_owner: owner,
    vendor_name: vendor,
    invoice_number: invoiceNumber,
    invoice_date: id === 'doc-acme' ? '2026-07-16' : '2026-07-12',
    due_date: dueDate,
    total,
    currency: 'USD',
    created_at: '2026-07-21T02:40:00Z',
    updated_at: status === 'exported' ? '2026-07-21T03:12:00Z' : '2026-07-21T03:00:00Z',
    validation_issue_count: issue ? 1 : 0,
    validation_error_count: issue ? 1 : 0,
    validation_codes: issue ? [issue] : [],
    has_validation_errors: Boolean(issue),
    export_state:
      status === 'exported' ? 'exported' : status === 'approved' ? 'eligible' : 'not_eligible',
    work_item_id: status === 'needs_review' ? `work-${id}` : null,
    correction_reason:
      status === 'needs_correction'
        ? 'Please correct the highlighted invoice value and submit it for review again.'
        : null,
  }
}

const invoices = invoiceSeeds.map(invoiceFromSeed)
const invoiceById = new Map(invoices.map((invoice) => [invoice.id, invoice]))

function extractionFor(invoice: InvoiceItem): InvoiceDetailResponse['extraction'] {
  const code = invoice.validation_codes[0]
  const fieldName =
    code === 'tax_amount_mismatch' ? 'tax' : code === 'total_mismatch' ? 'total' : 'invoice_number'
  return {
    data: {
      vendor_name: invoice.vendor_name,
      invoice_number: invoice.invoice_number,
      invoice_date: invoice.invoice_date,
      due_date: invoice.due_date,
      subtotal:
        invoice.id === 'doc-acme' ? '640.00' : String((Number(invoice.total) / 1.1).toFixed(2)),
      tax:
        invoice.id === 'doc-acme'
          ? '64.00'
          : String((Number(invoice.total) - Number(invoice.total) / 1.1).toFixed(2)),
      total: invoice.total,
      currency: invoice.currency,
      line_items:
        invoice.id === 'doc-acme'
          ? [
              {
                description: 'Professional services',
                quantity: '1',
                unit_price: '640.00',
                amount: '640.00',
              },
            ]
          : [
              {
                description: 'Invoice services',
                quantity: '1',
                unit_price: invoice.total,
                amount: invoice.total,
              },
            ],
    },
    confidence: [
      { field_name: 'vendor_name', score: 0.96, source_page: 1, source_text: invoice.vendor_name },
      {
        field_name: 'invoice_number',
        score: 0.94,
        source_page: 1,
        source_text: invoice.invoice_number,
      },
      { field_name: 'total', score: 0.98, source_page: 1, source_text: `Total ${invoice.total}` },
    ],
    validation: code
      ? [
          {
            field_name: fieldName,
            severity: 'error',
            code,
            message: findingLabels[code] ?? 'Invoice validation requires review.',
          },
        ]
      : [],
  }
}

function detailFor(invoice: InvoiceItem, approved = false): InvoiceDetailResponse {
  const document = approved
    ? {
        ...invoice,
        status: 'approved',
        business_status: 'approved',
        current_stage: 'approved',
        export_state: 'eligible' as const,
      }
    : invoice
  return {
    document,
    extraction: approved ? { ...extractionFor(invoice)!, validation: [] } : extractionFor(invoice),
    correction_summary:
      invoice.id === 'doc-acme'
        ? {
            latest_change_count: 1,
            latest_changed_fields: ['vendor_name'],
            latest_actor: 'Invoice Uploader',
            latest_reason: 'Matched the legal vendor name shown on the PDF.',
          }
        : null,
    audit_events: approved
      ? [
          {
            id: 'audit-upload',
            event_type: 'document_uploaded',
            actor: 'Invoice Uploader',
            new_status: 'uploaded',
            created_at: '2026-07-21T02:40:00Z',
          },
          {
            id: 'audit-read',
            event_type: 'processing_finished',
            actor: 'Document Reader',
            new_status: 'needs_review',
            created_at: '2026-07-21T02:41:00Z',
          },
          {
            id: 'audit-approved',
            event_type: 'document_approved',
            actor: 'James Smith',
            old_status: 'needs_review',
            new_status: 'approved',
            created_at: observedAt,
          },
        ]
      : [
          {
            id: `audit-${invoice.id}`,
            event_type: 'review_required',
            actor: 'Document Reader',
            new_status: invoice.status,
            created_at: '2026-07-21T02:42:00Z',
          },
        ],
  }
}

const reviewItems: ReviewQueueItem[] = invoices
  .filter((invoice) => ['needs_review', 'needs_correction'].includes(invoice.business_status))
  .map((invoice, index) => ({
    id: invoice.id,
    original_filename: invoice.original_filename,
    invoice_number: invoice.invoice_number,
    vendor_name: invoice.vendor_name,
    total: invoice.total,
    currency: invoice.currency,
    invoice_date: invoice.invoice_date,
    due_date: invoice.due_date,
    owner: invoice.current_owner,
    risk: invoice.has_validation_errors ? (index % 2 ? 'medium' : 'high') : 'low',
    confidence: [0.92, 0.86, 0.78, 0.97, 0.88, 0.8][index] ?? 0.9,
    finding: findingLabels[invoice.validation_codes[0]] ?? 'Review extracted invoice data',
    blocker_count: invoice.validation_error_count,
    issue_count: invoice.validation_issue_count,
    can_approve: !invoice.has_validation_errors,
    recommended_action: invoice.has_validation_errors ? 'request_correction' : 'review',
    age_seconds: [1080, 7200, 18000, 21600, 86400, 172800][index] ?? 3600,
    created_at: invoice.created_at,
    updated_at: invoice.updated_at,
  }))

const exceptionItems: ExceptionItem[] = reviewItems
  .filter((item) => item.issue_count)
  .map((item, index) => ({
    id: `exception-${item.id}`,
    document_id: item.id,
    work_item_id: `work-${item.id}`,
    original_filename: item.original_filename,
    invoice_number: item.invoice_number,
    vendor_name: item.vendor_name,
    total: item.total,
    currency: item.currency,
    issue: item.finding ?? 'Invoice validation issue',
    category:
      index === 0
        ? 'vendor_invoice'
        : index === 1 || index === 4
          ? 'tax_amount'
          : index === 2
            ? 'duplicate'
            : 'dates_details',
    risk: item.risk === 'high' ? 'high' : 'medium',
    blocks_approval: true,
    owner: item.owner,
    detected_at: '2026-07-21T02:42:00Z',
    age_seconds: item.age_seconds,
  }))

function exceptionDetail(item: ExceptionItem): ExceptionDetail {
  return {
    ...item,
    message: `${item.issue} was detected during deterministic invoice validation.`,
    code: invoiceById.get(item.document_id)?.validation_codes[0] ?? 'validation_issue',
    field_name: item.issue.toLowerCase().includes('tax') ? 'tax' : 'total',
    field_value: null,
    required_action: 'Correct the invoice data and run validation again before approval.',
    related_checks: [
      { label: 'Invoice extracted', status: 'passed' },
      { label: 'Vendor matched', status: 'passed' },
      { label: item.issue, status: 'blocked' },
    ],
  }
}

const activeBatchDocumentIds = new Set(['doc-acme-approved'])

function exportStateForInvoice(invoice: InvoiceItem): ExportView {
  if (invoice.business_status === 'exported') return 'exported'
  if (activeBatchDocumentIds.has(invoice.id)) return 'in_batch'
  if (invoice.business_status === 'approved' && !invoice.has_validation_errors) return 'ready'
  return 'blocked'
}

const exportItems: ExportInvoiceItem[] = invoices.map((invoice, index) => {
  const status = exportStateForInvoice(invoice)
  const approved = ['ready', 'in_batch', 'exported'].includes(status)
  return {
    id: invoice.id,
    invoice_label: invoice.invoice_number ?? invoice.original_filename,
    filename: invoice.original_filename,
    vendor_name: invoice.vendor_name,
    approved_by: approved ? (index % 2 ? 'Alex Davis' : 'James Smith') : null,
    approved_at: approved ? '2026-07-21T02:50:00Z' : null,
    total: invoice.total,
    currency: invoice.currency,
    status,
    issue:
      status === 'blocked'
        ? (findingLabels[invoice.validation_codes[0]] ?? 'Waiting for reviewer approval')
        : null,
    batch_id:
      status === 'in_batch' ? 'batch-july' : status === 'exported' ? 'batch-completed' : null,
    updated_at: invoice.updated_at,
  }
})

const recentRuns: ExportRun[] = [
  {
    id: 'run-success',
    batch_id: 'batch-completed',
    status: 'succeeded',
    destination: 'csv',
    destination_label: 'CSV download',
    format: 'csv',
    actor: 'James Smith',
    invoice_count: 3,
    total_amount: '17885.50',
    currency: 'USD',
    attempt_count: 1,
    file_name: 'invoices-2026-07-21.csv',
    download_available: true,
    error_code: null,
    error_message: null,
    retryable: false,
    created_at: '2026-07-21T02:55:00Z',
    completed_at: '2026-07-21T02:55:08Z',
    stages: [
      { label: 'Eligibility checked', status: 'completed' },
      { label: 'CSV generated', status: 'completed' },
      { label: 'Audit recorded', status: 'completed' },
    ],
  },
  {
    id: 'run-failed',
    batch_id: 'batch-failed',
    status: 'failed',
    destination: 'csv',
    destination_label: 'CSV download',
    format: 'csv',
    actor: 'Alex Davis',
    invoice_count: 2,
    total_amount: '5117.50',
    currency: 'USD',
    attempt_count: 2,
    file_name: null,
    download_available: false,
    error_code: 'export_timeout',
    error_message: 'The export file could not be finalized.',
    retryable: true,
    created_at: '2026-07-21T02:20:00Z',
    completed_at: '2026-07-21T02:21:02Z',
    stages: [
      { label: 'Eligibility checked', status: 'completed' },
      { label: 'CSV generated', status: 'failed' },
      { label: 'Audit recorded', status: 'not_started' },
    ],
  },
]

const activeBatch: ExportBatch = {
  id: 'batch-july',
  name: 'July approved invoices',
  status: 'ready',
  destination: 'csv',
  destination_label: 'CSV download',
  format: 'csv',
  created_by: 'James Smith',
  invoice_count: exportItems.filter((item) => item.status === 'in_batch').length,
  total_amount: exportMetric('in_batch').amount,
  currency: 'USD',
  invoices: exportItems.filter((item) => item.status === 'in_batch'),
  eligibility: [
    {
      code: 'approved',
      label: 'All invoices are approved',
      state: 'passed',
      detail: 'Every selected invoice has a recorded reviewer approval.',
    },
    {
      code: 'blockers',
      label: 'No unresolved blockers',
      state: 'passed',
      detail: 'No error-level validation issue remains.',
    },
    {
      code: 'duplicate_export',
      label: 'No previous successful export',
      state: 'passed',
      detail: 'The selected invoices were not exported before.',
    },
  ],
  last_run_id: null,
  created_at: '2026-07-21T03:02:00Z',
  updated_at: '2026-07-21T03:05:00Z',
}

function exportMetric(status: Exclude<ExportView, 'drafts'>) {
  const items = exportItems.filter((item) => item.status === status)
  const currencies = new Set(items.map((item) => item.currency).filter(Boolean))
  const amount = items.reduce((sum, item) => sum + Number(item.total ?? 0), 0)
  return {
    count: items.length,
    amount: amount.toFixed(2),
    currency: currencies.size === 1 ? ([...currencies][0] ?? null) : null,
  }
}

function invoiceListFixture(params = new URLSearchParams()): InvoiceListResponse {
  const requestedStatus = params.get('status')
  const status = isInvoiceLifecycleFilter(requestedStatus) ? requestedStatus : ''
  const search = (params.get('search') ?? '').trim().toLowerCase()
  const vendor = (params.get('vendor') ?? '').trim().toLowerCase()
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const pageSize = Math.max(1, Number(params.get('page_size') ?? 10))
  const filtered = invoices.filter(
    (invoice) =>
      belongsToInvoiceLifecycle(invoice, status) &&
      (!search ||
        [invoice.invoice_number, invoice.vendor_name, invoice.original_filename]
          .join(' ')
          .toLowerCase()
          .includes(search)) &&
      (!vendor || (invoice.vendor_name ?? '').toLowerCase().includes(vendor)),
  )
  const lifecycleCount = (value: Parameters<typeof belongsToInvoiceLifecycle>[1]) =>
    invoices.filter((invoice) => belongsToInvoiceLifecycle(invoice, value)).length
  return {
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    page,
    page_size: pageSize,
    total: filtered.length,
    total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    summary: {
      all: invoices.length,
      waiting_review: lifecycleCount('needs_review'),
      needs_correction: lifecycleCount('needs_correction'),
      approved: lifecycleCount('approved'),
      exported: lifecycleCount('exported'),
    },
    insights: { flagged: 8, duplicates_suspected: 3, tax_amount_issues: 2 },
  }
}

function reviewFixture(params = new URLSearchParams()): ReviewWorklist {
  const scope = params.get('scope') ?? 'all'
  const search = (params.get('search') ?? '').trim().toLowerCase()
  const risk = params.get('risk') ?? ''
  const owner = (params.get('owner') ?? '').trim().toLowerCase()
  const vendor = (params.get('vendor') ?? '').trim().toLowerCase()
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const pageSize = Math.max(1, Number(params.get('page_size') ?? 10))
  const filtered = reviewItems.filter(
    (item) =>
      (scope === 'all' ||
        (scope === 'decision' ? isDecisionQueueItem(item) : !isDecisionQueueItem(item))) &&
      (!search ||
        [item.invoice_number, item.vendor_name, item.original_filename]
          .join(' ')
          .toLowerCase()
          .includes(search)) &&
      (!risk || item.risk === risk) &&
      (!owner || (item.owner ?? '').toLowerCase().includes(owner)) &&
      (!vendor || (item.vendor_name ?? '').toLowerCase().includes(vendor)),
  )
  return {
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    page,
    page_size: pageSize,
    total: filtered.length,
    total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    summary: {
      in_queue: filtered.length,
      high_risk: filtered.filter((item) => item.risk === 'high').length,
      invoice_due_today: filtered.filter((item) => item.due_date === '2026-07-23').length,
      average_review_seconds: filtered.length
        ? Math.round(filtered.reduce((sum, item) => sum + item.age_seconds, 0) / filtered.length)
        : 0,
    },
  }
}

function exceptionsFixture(params = new URLSearchParams()): ExceptionListResponse {
  const search = (params.get('search') ?? '').trim().toLowerCase()
  const risk = params.get('risk') ?? ''
  const owner = (params.get('owner') ?? '').trim().toLowerCase()
  const category = params.get('category') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const pageSize = Math.max(1, Number(params.get('page_size') ?? 10))
  const filtered = exceptionItems.filter(
    (item) =>
      item.blocks_approval &&
      (!search ||
        [item.invoice_number, item.vendor_name, item.issue]
          .join(' ')
          .toLowerCase()
          .includes(search)) &&
      (!risk || item.risk === risk) &&
      (!owner || (item.owner ?? '').toLowerCase().includes(owner)) &&
      (!category || item.category === category),
  )
  const categories = exceptionItems.reduce<Record<string, number>>((counts, item) => {
    counts[item.category] = (counts[item.category] ?? 0) + 1
    return counts
  }, {})
  const issueCounts = exceptionItems.reduce<Record<string, number>>((counts, item) => {
    counts[item.issue] = (counts[item.issue] ?? 0) + 1
    return counts
  }, {})
  return {
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    page,
    page_size: pageSize,
    total: filtered.length,
    total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    summary: {
      open_exceptions: exceptionItems.length,
      high_risk: exceptionItems.filter((item) => item.risk === 'high').length,
      warning_issues: exceptionItems.filter((item) => item.risk !== 'high').length,
      invoices_affected: new Set(exceptionItems.map((item) => item.document_id)).size,
      categories: {
        vendor_invoice: categories.vendor_invoice ?? 0,
        tax_amount: categories.tax_amount ?? 0,
        duplicate: categories.duplicate ?? 0,
        dates_details: categories.dates_details ?? 0,
        other: categories.other ?? 0,
      },
      top_issues: Object.entries(issueCounts)
        .sort((left, right) => right[1] - left[1])
        .slice(0, 3)
        .map(([label, count]) => ({
          label,
          category: exceptionItems.find((item) => item.issue === label)?.category ?? 'other',
          count,
        })),
    },
    assignee_options: ['James Smith', 'Alex Davis', 'Kelly Morgan'],
    capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
  }
}

function exportFixture(params = new URLSearchParams()): ExportWorkspaceResponse {
  const requestedView = params.get('view')
  const view = isExportView(requestedView) ? requestedView : 'ready'
  const search = (params.get('search') ?? '').trim().toLowerCase()
  const vendor = (params.get('vendor') ?? '').trim().toLowerCase()
  const currency = (params.get('currency') ?? '').trim().toLowerCase()
  const approvedBy = (params.get('approved_by') ?? '').trim().toLowerCase()
  const page = Math.max(1, Number(params.get('page') ?? 1))
  const pageSize = Math.max(1, Number(params.get('page_size') ?? 10))
  const filtered = exportItems.filter(
    (item) =>
      belongsToExportView(item, view) &&
      (!search ||
        [item.invoice_label, item.filename, item.vendor_name]
          .join(' ')
          .toLowerCase()
          .includes(search)) &&
      (!vendor || (item.vendor_name ?? '').toLowerCase().includes(vendor)) &&
      (!currency || (item.currency ?? '').toLowerCase() === currency) &&
      (!approvedBy || (item.approved_by ?? '').toLowerCase().includes(approvedBy)),
  )
  return {
    capabilities: {
      destinations: [{ id: 'csv', label: 'CSV download', formats: ['csv'], mode: 'download' }],
      scheduling: false,
      drafts: true,
      retry: true,
      configured_provider: 'Local CSV',
      destination_available: true,
    },
    summary: {
      ready: exportMetric('ready'),
      in_batch: exportMetric('in_batch'),
      exported: exportMetric('exported'),
      blocked: exportMetric('blocked'),
    },
    items: filtered.slice((page - 1) * pageSize, page * pageSize),
    page,
    page_size: pageSize,
    total: filtered.length,
    total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    filters: {
      vendors: [...new Set(exportItems.map((item) => item.vendor_name).filter(Boolean))].sort(),
      currencies: [...new Set(exportItems.map((item) => item.currency).filter(Boolean))].sort(),
      approvers: [...new Set(exportItems.map((item) => item.approved_by).filter(Boolean))].sort(),
    },
    batch: activeBatch,
    recent_runs: recentRuns,
  }
}

function evaluationFixture(): EvaluationDashboard {
  const runDates = [
    '2026-05-16',
    '2026-05-30',
    '2026-06-13',
    '2026-06-26',
    '2026-07-03',
    '2026-07-10',
    '2026-07-18',
  ]
  const runs = runDates.map((date, index) => ({
    id: `eval-${index + 1}`,
    label: `Invoice scenarios v1 / run ${index + 1}`,
    dataset_id: 'invoice-scenarios',
    dataset_version: 'v1',
    dataset_class: 'synthetic',
    split: 'test',
    provider: 'openai',
    source: 'evaluation_harness',
    source_document: null,
    observed_at: `${date}T03:00:00Z`,
    documents: 20,
    fields_matched: index === 6 ? 160 : 151 + index,
    fields_total: 160,
    field_match: [0.964, 0.96, 0.968, 0.974, 0.973, 0.972, 1][index],
    validation_match: [0.951, 0.95, 0.954, 0.96, 0.961, 0.966, 1][index],
    document_exact_match: index === 6 ? 1 : 0.9,
    approval_blocker_accuracy: index === 6 ? 1 : 0.95,
    provider_errors: 0,
    duration_seconds: index === 6 ? 24 : 22 + index,
    duration_kind: 'wall_clock' as const,
    provider_calls: 20,
    estimated_cost_usd: index === 6 ? 0.08 : 0.07,
    cost_status: 'estimated',
    cost_claim: 'Estimated from recorded provider usage.',
    passed: true,
    verdict_available: true,
    by_field: {
      vendor_name: 1,
      invoice_number: 1,
      invoice_date: 1,
      due_date: 1,
      subtotal: 1,
      total: index === 6 ? 1 : 0.99,
      tax: index === 6 ? 1 : 0.95,
      currency: 1,
    },
    failure_taxonomy: {},
    limitations: [
      'Results are from labeled synthetic invoice documents.',
      'Small sample size; use for directional engineering evidence.',
      'English invoices only.',
      'No customer validation has been performed.',
    ],
    is_current: index === 6,
  }))
  const selected = runs[6]
  const comparison = runs[3]
  const fieldLabels: Record<string, string> = {
    vendor_name: 'Vendor',
    invoice_number: 'Invoice number',
    invoice_date: 'Invoice date',
    due_date: 'Due date',
    subtotal: 'Subtotal',
    tax: 'Tax',
    total: 'Total amount',
    currency: 'Currency',
  }
  const fields = Object.entries(fieldLabels).map(([field, label]) => {
    const current = selected.by_field[field] ?? null
    const previous = comparison.by_field[field] ?? null
    const deltaPp =
      current == null || previous == null ? null : Math.round((current - previous) * 10_000) / 100
    const status =
      deltaPp == null
        ? 'excluded'
        : deltaPp > 1
          ? 'improved'
          : deltaPp < -1
            ? 'regressed'
            : 'stable'
    return {
      field,
      label,
      current,
      previous,
      delta_pp: deltaPp,
      status,
      current_matches: current == null ? null : Math.round(current * selected.documents),
      current_denominator: selected.documents,
      previous_matches: previous == null ? null : Math.round(previous * comparison.documents),
      previous_denominator: comparison.documents,
    } satisfies EvaluationDashboard['fields'][number]
  })
  const regressionCounts = fields.reduce(
    (counts, field) => {
      if (field.status === 'improved') counts.improved += 1
      else if (field.status === 'regressed') counts.regressed += 1
      else if (field.status === 'stable') counts.stable += 1
      else counts.excluded += 1
      return counts
    },
    { improved: 0, stable: 0, regressed: 0, excluded: 0 },
  )
  return {
    gates: { field_match: 0.95, validation_match: 0.95, regression_tolerance_pp: 1 },
    preflight: {
      dataset_id: 'invoice-scenarios',
      dataset_version: 'v1',
      dataset_label: 'Synthetic invoice scenarios',
      available_documents: 20,
      documents: 20,
      limited: false,
      provider_calls_estimate: 20,
      estimated_cost_usd: 0.08,
      cost_note: 'List-price estimate before execution.',
      runnable: true,
      provider: 'OpenAI extraction provider',
    },
    runs: runs.map((run) => ({
      id: run.id,
      label: run.label,
      dataset_id: run.dataset_id,
      split: run.split,
      observed_at: run.observed_at,
      passed: run.passed,
      verdict_available: run.verdict_available,
      current: run.is_current,
    })),
    selected_run: selected,
    trend: runs.map((run) => ({
      id: run.id,
      observed_at: run.observed_at,
      field_match: run.field_match,
      validation_match: run.validation_match,
      documents: run.documents,
      provider_errors: 0,
      estimated_cost_usd: run.estimated_cost_usd,
      selected: run.is_current,
    })),
    regression: {
      comparison_run_id: 'eval-4',
      comparison_observed_at: '2026-06-26T03:00:00Z',
      tolerance_pp: 1,
      comparable_fields: fields.length - regressionCounts.excluded,
      improved: regressionCounts.improved,
      stable: regressionCounts.stable,
      regressed: regressionCounts.regressed,
      new_fields: 0,
      excluded_fields: regressionCounts.excluded,
      new_failures: 0,
    },
    fields,
    scenario_coverage: {
      dataset_id: 'invoice-scenarios',
      dataset_version: 'v1',
      claim_boundary: 'Synthetic labeled evidence only; this is not production accuracy.',
      included_in_selected_run: true,
      groups: [
        ['clean', 'Clean invoices', 5, 5],
        ['missing', 'Missing fields', 4, 5],
        ['totals', 'Total mismatches', 3, 5],
        ['duplicates', 'Duplicates', 2, 5],
        ['scans', 'Low-quality scans', 3, 5],
        ['multipage', 'Multi-page / rotated', 3, 5],
      ].map(([id, label, current, target]) => ({
        id: String(id),
        label: String(label),
        current: Number(current),
        target: Number(target),
        coverage: Number(current) / Number(target),
        remaining: Number(target) - Number(current),
        case_ids: Array.from({ length: Number(current) }, (_, index) => `${id}-${index + 1}`),
      })),
    },
    attempts: [
      {
        id: 'attempt-current',
        status: 'succeeded',
        dataset_id: 'invoice-scenarios',
        dataset_version: 'v1',
        documents_requested: 20,
        documents_processed: 20,
        provider_calls: 20,
        run_id: 'eval-7',
        error_code: null,
        error_message: null,
        requested_by: 'James Smith',
        started_at: '2026-07-18T03:00:00Z',
        completed_at: '2026-07-18T03:00:24Z',
      },
    ],
  }
}

function systemFixture(): SystemDashboard {
  return {
    observed_at: observedAt,
    freshness: { state: 'current', label: 'Observed one minute ago' },
    overall: {
      status: 'degraded',
      title: 'Operational with one degraded service',
      detail:
        'Invoice upload, reading, extraction, review, and storage are healthy. CSV export needs attention.',
    },
    kpis: { processing_now: 3, waiting: 5, completed_today: 48, needs_attention: 1 },
    services: [
      [
        'uploads',
        'Uploads',
        'Built-in upload service',
        'operational',
        '142 files uploaded',
        null,
        'Invoice upload remains available.',
      ],
      [
        'invoice_reading',
        'Invoice reading',
        'Mistral OCR',
        'operational',
        '138 documents read',
        null,
        'PDF reading remains available.',
      ],
      [
        'data_extraction',
        'Data extraction',
        'OpenAI',
        'operational',
        '128 invoices extracted',
        null,
        'Structured extraction remains available.',
      ],
      [
        'document_storage',
        'Document storage',
        'Local workspace storage',
        'operational',
        '98.7% capacity available',
        null,
        'Stored invoice files remain available.',
      ],
      [
        'accounting_export',
        'Accounting export',
        'Local CSV',
        'degraded',
        'Last attempt timed out',
        'New export execution is temporarily affected.',
        'Upload, review, and previous export downloads remain available.',
      ],
    ].map(([id, name, provider, status, activity, affected, unaffected]) => ({
      id: String(id),
      name: String(name),
      provider: String(provider),
      status: status as 'operational' | 'degraded',
      uptime: null,
      uptime_label: 'Not enough history',
      observed_at: '2026-07-21T03:14:00Z',
      activity: String(activity),
      evidence: `${name} returned a sanitized ${status} observation.`,
      affected_capability: affected ? String(affected) : null,
      unaffected_capability: String(unaffected),
    })),
    alerts: [
      {
        id: 'alert-export',
        kind: 'service',
        target_id: 'accounting_export',
        severity: 'warning',
        title: 'Accounting export degraded',
        detail: 'Last attempt timed out. Review the service evidence before retrying.',
      },
    ],
    flow: {
      window_label: 'Today',
      denominator: 'Percentages compare each stage with the uploaded cohort.',
      stages: [
        {
          id: 'uploaded',
          label: 'Upload received',
          count: 52,
          previous_count: null,
          conversion_percent: 100,
        },
        {
          id: 'pdf_read',
          label: 'PDF read',
          count: 51,
          previous_count: 52,
          conversion_percent: 98,
        },
        {
          id: 'extracted',
          label: 'Data extracted',
          count: 48,
          previous_count: 51,
          conversion_percent: 94,
        },
        {
          id: 'validated',
          label: 'Checks completed',
          count: 48,
          previous_count: 48,
          conversion_percent: 100,
        },
        {
          id: 'export_attempted',
          label: 'Export attempted',
          count: 47,
          previous_count: 48,
          conversion_percent: 98,
        },
        {
          id: 'export_succeeded',
          label: 'Export succeeded',
          count: 46,
          previous_count: 47,
          conversion_percent: 98,
        },
      ],
    },
    recent_jobs: [
      ['job-1', 'doc-acme', 'INV-2026-04567', 'Reading PDF', 'succeeded', 12000, 1, false, null],
      [
        'job-2',
        'doc-northstar',
        'INV-2026-04568',
        'Extracting data',
        'running',
        null,
        1,
        false,
        null,
      ],
      [
        'job-3',
        'doc-meridian',
        'INV-2026-04569',
        'Validating invoice',
        'queued',
        null,
        0,
        false,
        null,
      ],
      [
        'job-4',
        'doc-greenline-approved',
        'INV-2026-04573',
        'Preparing export',
        'succeeded',
        18000,
        1,
        false,
        null,
      ],
      [
        'job-5',
        'doc-northstar-exported',
        'INV-2026-04574',
        'Preparing export',
        'failed',
        62000,
        2,
        true,
        'The CSV file could not be finalized.',
      ],
    ].map(
      (
        [id, documentId, invoice, stage, status, duration, attempts, retryable, failure],
        index,
      ) => ({
        id: String(id),
        document_id: String(documentId),
        invoice: String(invoice),
        filename: `${String(invoice).toLowerCase()}.pdf`,
        stage: String(stage),
        status: status as 'succeeded' | 'running' | 'queued' | 'failed',
        started_at: `2026-07-21T0${3 - Math.min(index, 2)}:${String(14 - index * 2).padStart(2, '0')}:00Z`,
        finished_at: status === 'running' || status === 'queued' ? null : '2026-07-21T03:14:18Z',
        duration_ms: duration == null ? null : Number(duration),
        attempt_count: Number(attempts),
        retryable: Boolean(retryable),
        failure_summary: failure ? String(failure) : null,
      }),
    ),
    integrations: [
      {
        id: 'invoice_reading',
        name: 'Document reader',
        provider: 'Mistral OCR',
        status: 'operational',
        observed_at: '2026-07-21T03:14:00Z',
        evidence: 'Latest observed request succeeded.',
      },
      {
        id: 'data_extraction',
        name: 'Data extractor',
        provider: 'OpenAI',
        status: 'operational',
        observed_at: '2026-07-21T03:14:00Z',
        evidence: 'Latest observed extraction succeeded.',
      },
      {
        id: 'document_storage',
        name: 'File storage',
        provider: 'Local workspace storage',
        status: 'operational',
        observed_at: '2026-07-21T03:14:00Z',
        evidence: 'Storage is writable.',
      },
      {
        id: 'accounting_export',
        name: 'Accounting export',
        provider: 'Local CSV',
        status: 'degraded',
        observed_at: '2026-07-21T03:14:00Z',
        evidence: 'Latest export attempt failed safely.',
      },
    ],
    audit: [
      {
        id: 'audit-1',
        timestamp: '2026-07-21T03:12:00Z',
        actor: 'James Smith',
        action: 'Invoice approved',
        target: 'INV-2026-04570',
        result: 'success',
      },
      {
        id: 'audit-2',
        timestamp: '2026-07-21T02:57:00Z',
        actor: 'Alex Davis',
        action: 'Correction requested',
        target: 'INV-2026-04571',
        result: 'recorded',
      },
      {
        id: 'audit-3',
        timestamp: '2026-07-21T02:55:08Z',
        actor: 'James Smith',
        action: 'Export completed',
        target: 'invoices-2026-07-21.csv',
        result: 'success',
      },
    ],
    maintenance: {
      scheduled: false,
      title: 'No maintenance scheduled',
      detail: 'All application components are up to date.',
    },
  }
}

export async function installPortfolioApi(
  page: Page,
  initialRole: PortfolioRole = 'administrator',
) {
  let role = initialRole
  let cleanApproved = false
  await page.route('**/*', async (route) => {
    const request = route.request()
    const { pathname, searchParams } = new URL(request.url())
    if (pathname === '/auth/session') {
      const actor =
        role === 'administrator'
          ? 'James Smith'
          : role === 'reviewer'
            ? 'Alex Davis'
            : 'Invoice Uploader'
      return route.fulfill({
        json: {
          authenticated: true,
          actor,
          user_id: `portfolio-${role}`,
          workspace_id: 'portfolio',
          role,
          is_admin: role === 'administrator',
        },
      })
    }
    if (request.resourceType() === 'document') return route.continue()
    if (pathname === '/backoffice/workspace')
      return route.fulfill({
        json: {
          workspace_id: 'portfolio',
          work_items: [],
          pending_approvals: [],
          documents: invoices,
          metrics: {},
        },
      })
    if (pathname === '/invoices') return route.fulfill({ json: invoiceListFixture(searchParams) })
    if (pathname === '/review/worklist') return route.fulfill({ json: reviewFixture(searchParams) })
    if (pathname === '/exceptions') return route.fulfill({ json: exceptionsFixture(searchParams) })
    if (pathname === '/exports/workspace')
      return route.fulfill({ json: exportFixture(searchParams) })
    if (pathname === '/evaluation/dashboard') return route.fulfill({ json: evaluationFixture() })
    if (pathname === '/system/dashboard') return route.fulfill({ json: systemFixture() })
    if (pathname === '/operations/notifications')
      return route.fulfill({ json: { notifications: [], unread_count: 3 } })
    if (pathname === '/providers/health')
      return route.fulfill({ json: { overall_status: 'degraded', providers: [] } })
    if (pathname === '/operations/jobs')
      return route.fulfill({
        json: {
          worker: {
            status: 'healthy',
            queued_jobs: 5,
            failed_jobs: 1,
            stalled_jobs: 0,
            evidence: 'Worker heartbeat observed.',
          },
          failed_jobs: [],
        },
      })
    if (pathname.startsWith('/exceptions/')) {
      const id = pathname.split('/')[2]
      const item = exceptionItems.find((candidate) => candidate.id === id)
      if (item) return route.fulfill({ json: { exception: exceptionDetail(item) } })
    }
    if (pathname.startsWith('/exports/runs/')) {
      const id = pathname.split('/')[3]
      const run = recentRuns.find((candidate) => candidate.id === id)
      if (run) return route.fulfill({ json: { run } })
    }
    const workflowMatch = pathname.match(/^\/documents\/([^/]+)\/workflow$/)
    if (workflowMatch) {
      const invoice = invoiceById.get(workflowMatch[1])
      const workflow: ReviewWorkflow = {
        current_stage:
          cleanApproved && invoice?.id === 'doc-acme'
            ? 'approved'
            : (invoice?.current_stage ?? 'needs_review'),
        current_owner: invoice?.current_owner ?? 'Finance reviewer',
        waiting_for: invoice?.status === 'needs_review' ? 'Reviewer decision' : 'Nothing',
        next_action: invoice?.has_validation_errors ? 'Request correction' : 'Review invoice',
        attention_reason: invoice?.validation_codes[0]
          ? findingLabels[invoice.validation_codes[0]]
          : null,
        work_item: { assignee: invoice?.current_owner },
      }
      return route.fulfill({ json: workflow })
    }
    const contentMatch = pathname.match(/^\/documents\/([^/]+)\/content$/)
    if (contentMatch)
      return route.fulfill({
        contentType: 'application/pdf',
        body: contentMatch[1].includes('meridian') ? duplicatePdf : cleanPdf,
      })
    const documentMatch = pathname.match(/^\/documents\/([^/]+)$/)
    if (documentMatch) {
      const invoice = invoiceById.get(documentMatch[1])
      if (invoice)
        return route.fulfill({
          json: detailFor(invoice, cleanApproved && invoice.id === 'doc-acme'),
        })
    }
    if (pathname === '/review/doc-acme/approve' && request.method() === 'POST') {
      cleanApproved = true
      return route.fulfill({
        json: {
          document: { id: 'doc-acme', status: 'approved', updated_at: observedAt },
          review_task: {
            status: 'approved',
            reviewer_notes: '',
            reviewed_by: 'James Smith',
            reviewed_at: observedAt,
          },
          decision: {
            status: 'approved',
            actor: 'James Smith',
            recorded_at: observedAt,
            note: '',
            audit_event_count: 3,
            export_eligibility: 'eligible',
          },
        },
      })
    }
    if (
      pathname.startsWith('/review/') &&
      pathname.endsWith('/save') &&
      request.method() === 'POST'
    )
      return route.fulfill({ json: { saved: true } })
    if (
      pathname.startsWith('/invoices/') &&
      pathname.endsWith('/request-correction') &&
      request.method() === 'POST'
    )
      return route.fulfill({ json: { status: 'correction_requested' } })
    if (
      pathname.startsWith('/invoices/') &&
      pathname.endsWith('/draft') &&
      request.method() === 'POST'
    )
      return route.fulfill({ json: { status: 'needs_review' } })
    return route.continue()
  })

  return {
    setRole(nextRole: PortfolioRole) {
      role = nextRole
    },
    setApproved(value: boolean) {
      cleanApproved = value
    },
  }
}
