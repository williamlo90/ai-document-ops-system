import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'

import type { EvaluationDashboard } from '../src/features/evaluation/types'
import type { ExceptionDetail, ExceptionItem, ExceptionListResponse } from '../src/features/exceptions/types'
import type { ExportBatch, ExportInvoiceItem, ExportRun, ExportWorkspaceResponse } from '../src/features/exports/types'
import type { InvoiceDetailResponse, InvoiceItem, InvoiceListResponse } from '../src/features/invoices/types'
import type { OverviewDashboard } from '../src/features/overview/types'
import type { ReviewQueueItem, ReviewWorklist, ReviewWorkflow } from '../src/features/review/types'
import type { SystemDashboard } from '../src/features/system/types'

export type PortfolioRole = 'administrator' | 'reviewer' | 'uploader'

const observedAt = '2026-07-21T03:15:00Z'
const cleanPdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_original.pdf'))
const duplicatePdf = readFileSync(path.resolve('../examples/benchmark/datasets/invoice_scenarios_v1/documents/duplicate_copy.pdf'))

const invoiceSeeds = [
  ['doc-acme', 'SIP-7788', 'Summit Industrial Parts', '704.00', 'needs_review', 'James Smith', '2026-08-15', 'po_number_missing'],
  ['doc-northstar', 'INV-2026-04568', 'Northstar Office', '3275.40', 'needs_review', 'Alex Davis', '2026-07-20', 'tax_amount_mismatch'],
  ['doc-meridian', 'INV-2026-04569', 'Meridian Freight', '8600.75', 'needs_review', 'Kelly Morgan', '2026-07-21', 'duplicate_invoice'],
  ['doc-acme-approved', 'INV-2026-04570', 'Acme Logistics', '6120.00', 'approved', 'James Smith', '2026-07-21', ''],
  ['doc-northstar-correction', 'INV-2026-04571', 'Northstar Office', '1842.10', 'needs_correction', 'Alex Davis', '2026-07-22', 'receipt_required'],
  ['doc-meridian-correction', 'INV-2026-04572', 'Meridian Freight', '4950.00', 'needs_correction', 'Kelly Morgan', '2026-07-22', 'total_mismatch'],
  ['doc-greenline-approved', 'INV-2026-04573', 'Greenline Supply', '2315.50', 'approved', 'James Smith', '2026-07-23', ''],
  ['doc-northstar-exported', 'INV-2026-04574', 'Northstar Office', '910.25', 'exported', 'Alex Davis', '2026-07-23', ''],
] as const

const findingLabels: Record<string, string> = {
  po_number_missing: 'PO number missing',
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
    current_stage: status === 'needs_correction' ? 'correction_requested' : status === 'needs_review' ? 'needs_review' : status,
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
    export_state: status === 'exported' ? 'exported' : status === 'approved' ? 'eligible' : 'not_eligible',
    work_item_id: status === 'needs_review' ? `work-${id}` : null,
    correction_reason: status === 'needs_correction' ? 'Please add the supporting document and correct the value highlighted by validation.' : null,
  }
}

const invoices = invoiceSeeds.map(invoiceFromSeed)
const invoiceById = new Map(invoices.map((invoice) => [invoice.id, invoice]))

function extractionFor(invoice: InvoiceItem): InvoiceDetailResponse['extraction'] {
  const code = invoice.validation_codes[0]
  const fieldName = code === 'po_number_missing' ? 'po_number' : code === 'tax_amount_mismatch' ? 'tax' : code === 'total_mismatch' ? 'total' : 'invoice_number'
  return {
    data: {
      vendor_name: invoice.vendor_name,
      invoice_number: invoice.invoice_number,
      invoice_date: invoice.invoice_date,
      due_date: invoice.due_date,
      subtotal: invoice.id === 'doc-acme' ? '640.00' : String((Number(invoice.total) / 1.1).toFixed(2)),
      tax: invoice.id === 'doc-acme' ? '64.00' : String((Number(invoice.total) - Number(invoice.total) / 1.1).toFixed(2)),
      total: invoice.total,
      currency: invoice.currency,
      line_items: invoice.id === 'doc-acme'
        ? [
            { description: 'Professional services', quantity: '1', unit_price: '640.00', amount: '640.00' },
          ]
        : [{ description: 'Invoice services', quantity: '1', unit_price: invoice.total, amount: invoice.total }],
    },
    confidence: [
      { field_name: 'vendor_name', score: 0.96, source_page: 1, source_text: invoice.vendor_name },
      { field_name: 'invoice_number', score: 0.94, source_page: 1, source_text: invoice.invoice_number },
      { field_name: 'total', score: 0.98, source_page: 1, source_text: `Total ${invoice.total}` },
    ],
    validation: code ? [{
      field_name: fieldName,
      severity: 'error',
      code,
      message: findingLabels[code] ?? 'Invoice validation requires review.',
    }] : [],
  }
}

function detailFor(invoice: InvoiceItem, approved = false): InvoiceDetailResponse {
  const document = approved ? { ...invoice, status: 'approved', business_status: 'approved', current_stage: 'approved', export_state: 'eligible' as const } : invoice
  return {
    document,
    extraction: approved ? { ...extractionFor(invoice)!, validation: [] } : extractionFor(invoice),
    correction_summary: invoice.id === 'doc-acme'
      ? { latest_change_count: 1, latest_changed_fields: ['vendor_name'], latest_actor: 'Invoice Uploader', latest_reason: 'Matched the legal vendor name shown on the PDF.' }
      : null,
    audit_events: approved ? [
      { id: 'audit-upload', event_type: 'document_uploaded', actor: 'Invoice Uploader', new_status: 'uploaded', created_at: '2026-07-21T02:40:00Z' },
      { id: 'audit-read', event_type: 'processing_finished', actor: 'Document Reader', new_status: 'needs_review', created_at: '2026-07-21T02:41:00Z' },
      { id: 'audit-approved', event_type: 'document_approved', actor: 'James Smith', old_status: 'needs_review', new_status: 'approved', created_at: observedAt },
    ] : [
      { id: `audit-${invoice.id}`, event_type: 'review_required', actor: 'Document Reader', new_status: invoice.status, created_at: '2026-07-21T02:42:00Z' },
    ],
  }
}

const reviewItems: ReviewQueueItem[] = invoices.slice(0, 6).map((invoice, index) => ({
  id: invoice.id,
  original_filename: invoice.original_filename,
  invoice_number: invoice.invoice_number,
  vendor_name: invoice.vendor_name,
  total: invoice.total,
  currency: invoice.currency,
  invoice_date: invoice.invoice_date,
  due_date: invoice.due_date,
  owner: invoice.current_owner,
  risk: index === 0 || index === 3 ? 'high' : index === 1 || index === 4 ? 'medium' : 'low',
  confidence: [0.92, 0.86, 0.78, 0.91, 0.88, 0.80][index],
  finding: findingLabels[invoice.validation_codes[0]] ?? 'Review extracted invoice data',
  blocker_count: invoice.validation_error_count,
  issue_count: invoice.validation_issue_count,
  can_approve: !invoice.has_validation_errors,
  recommended_action: invoice.has_validation_errors ? 'request_correction' : 'review',
  age_seconds: [1080, 7200, 18000, 21600, 86400, 172800][index],
  created_at: invoice.created_at,
  updated_at: invoice.updated_at,
}))

const exceptionItems: ExceptionItem[] = reviewItems.filter((item) => item.issue_count).map((item, index) => ({
  id: `exception-${item.id}`,
  document_id: item.id,
  work_item_id: `work-${item.id}`,
  original_filename: item.original_filename,
  invoice_number: item.invoice_number,
  vendor_name: item.vendor_name,
  total: item.total,
  currency: item.currency,
  issue: item.finding ?? 'Invoice validation issue',
  category: index === 0 ? 'vendor_invoice' : index === 1 || index === 4 ? 'tax_amount' : index === 2 ? 'duplicate' : 'dates_details',
  risk: item.risk === 'high' ? 'high' : 'medium',
  blocks_approval: true,
  owner: item.owner,
  detected_at: '2026-07-21T02:42:00Z',
  age_seconds: item.age_seconds,
}))

function exceptionDetail(item: ExceptionItem): ExceptionDetail {
  return {
    ...item,
    message: item.issue === 'PO number missing'
      ? 'This invoice is missing a PO number required to match it to a purchase order.'
      : `${item.issue} was detected during deterministic invoice validation.`,
    code: invoiceById.get(item.document_id)?.validation_codes[0] ?? 'validation_issue',
    field_name: item.issue === 'PO number missing' ? 'po_number' : item.issue.toLowerCase().includes('tax') ? 'tax' : 'invoice_number',
    field_value: null,
    required_action: item.issue === 'PO number missing'
      ? 'Add a valid PO number or request it from the vendor, then run validation again.'
      : 'Correct the invoice data and run validation again before approval.',
    related_checks: [
      { label: 'Invoice extracted', status: 'passed' },
      { label: 'Vendor matched', status: 'passed' },
      { label: item.issue, status: 'blocked' },
    ],
  }
}

const exportItems: ExportInvoiceItem[] = invoices.slice(3).map((invoice, index) => ({
  id: invoice.id,
  invoice_label: invoice.invoice_number ?? invoice.original_filename,
  filename: invoice.original_filename,
  vendor_name: invoice.vendor_name,
  approved_by: index % 2 ? 'Alex Davis' : 'James Smith',
  approved_at: '2026-07-21T02:50:00Z',
  total: invoice.total,
  currency: invoice.currency,
  status: index === 0 || index === 2 ? 'ready' : index === 1 ? 'blocked' : 'exported',
  issue: index === 1 ? 'Correction is still required' : null,
  batch_id: index === 3 ? 'batch-completed' : null,
  updated_at: invoice.updated_at,
}))

const recentRuns: ExportRun[] = [
  {
    id: 'run-success', batch_id: 'batch-completed', status: 'succeeded', destination: 'csv', destination_label: 'CSV download', format: 'csv', actor: 'James Smith', invoice_count: 3,
    total_amount: '17885.50', currency: 'USD', attempt_count: 1, file_name: 'invoices-2026-07-21.csv', download_available: true,
    error_code: null, error_message: null, retryable: false, created_at: '2026-07-21T02:55:00Z', completed_at: '2026-07-21T02:55:08Z',
    stages: [{ label: 'Eligibility checked', status: 'completed' }, { label: 'CSV generated', status: 'completed' }, { label: 'Audit recorded', status: 'completed' }],
  },
  {
    id: 'run-failed', batch_id: 'batch-failed', status: 'failed', destination: 'csv', destination_label: 'CSV download', format: 'csv', actor: 'Alex Davis', invoice_count: 2,
    total_amount: '5117.50', currency: 'USD', attempt_count: 2, file_name: null, download_available: false,
    error_code: 'export_timeout', error_message: 'The export file could not be finalized.', retryable: true, created_at: '2026-07-21T02:20:00Z', completed_at: '2026-07-21T02:21:02Z',
    stages: [{ label: 'Eligibility checked', status: 'completed' }, { label: 'CSV generated', status: 'failed' }, { label: 'Audit recorded', status: 'not_started' }],
  },
]

const activeBatch: ExportBatch = {
  id: 'batch-july', name: 'July approved invoices', status: 'ready', destination: 'csv', destination_label: 'CSV download', format: 'csv', created_by: 'James Smith',
  invoice_count: 2, total_amount: '8435.50', currency: 'USD', invoices: exportItems.filter((item) => item.status === 'ready'),
  eligibility: [
    { code: 'approved', label: 'All invoices are approved', state: 'passed', detail: 'Every selected invoice has a recorded reviewer approval.' },
    { code: 'blockers', label: 'No unresolved blockers', state: 'passed', detail: 'No error-level validation issue remains.' },
    { code: 'duplicate_export', label: 'No previous successful export', state: 'passed', detail: 'The selected invoices were not exported before.' },
  ],
  last_run_id: null, created_at: '2026-07-21T03:02:00Z', updated_at: '2026-07-21T03:05:00Z',
}

function overviewFixture(): OverviewDashboard {
  return {
    observed_at: observedAt,
    actor: { name: 'James Smith', role: 'administrator' },
    briefing: { attention_count: 7, title: '7 invoices require attention today', detail: '3 have approval blockers and 4 need a reviewer decision.', action_label: 'Review urgent invoices', action_href: '/review-queue?risk=high' },
    kpis: [
      { id: 'waiting_review', label: 'Waiting for review', count: 24, note: '+4 since yesterday', tone: 'blue', href: '/review-queue' },
      { id: 'needs_correction', label: 'Needs correction', count: 16, note: '+3 since yesterday', tone: 'red', href: '/invoices?status=needs_correction' },
      { id: 'due_today', label: 'Due today', count: 7, note: '3 at high risk', tone: 'orange', href: '/review-queue?sort=due_date' },
      { id: 'ready_export', label: 'Ready to export', count: 12, note: '+2 since yesterday', tone: 'teal', href: '/exports' },
    ],
    findings: [
      { id: 'po', label: 'Potential PO mismatches', count: 8, tone: 'blue', href: '/exceptions?category=vendor_invoice' },
      { id: 'duplicate', label: 'Possible duplicates', count: 3, tone: 'purple', href: '/exceptions?category=duplicate' },
      { id: 'tax', label: 'Unusual tax amounts', count: 2, tone: 'orange', href: '/exceptions?category=tax_amount' },
    ],
    alerts: [
      { id: 'urgent', title: '3 invoices may miss review today', detail: 'High-risk invoices are still waiting for a decision.', severity: 'critical', href: '/review-queue?risk=high' },
      { id: 'correction', title: '2 high-risk corrections', detail: 'Uploader changes require reviewer confirmation.', severity: 'warning', href: '/invoices?status=needs_correction' },
      { id: 'po-alert', title: 'PO issues detected', detail: '8 invoices have vendor or PO validation findings.', severity: 'warning', href: '/exceptions?category=vendor_invoice' },
    ],
    queue: { total: 24, items: reviewItems.slice(0, 5).map((item) => ({ document_id: item.id, invoice_number: item.invoice_number ?? item.original_filename, vendor_name: item.vendor_name ?? 'Unknown vendor', total: item.total, currency: item.currency, finding: item.finding ?? 'Review invoice', risk: item.risk, confidence: item.confidence, due_date: item.due_date, owner: item.owner, recommended_action: item.recommended_action, href: `/review/${item.id}` })) },
    throughput: {
      window_label: 'Last 7 days', series: [{ id: 'processed', label: 'Processed' }, { id: 'sent_for_review', label: 'Sent for review' }],
      points: [
        { date: '2026-07-15', label: 'Jul 15', processed: 38, sent_for_review: 6 }, { date: '2026-07-16', label: 'Jul 16', processed: 52, sent_for_review: 8 },
        { date: '2026-07-17', label: 'Jul 17', processed: 61, sent_for_review: 7 }, { date: '2026-07-18', label: 'Jul 18', processed: 45, sent_for_review: 5 },
        { date: '2026-07-19', label: 'Jul 19', processed: 70, sent_for_review: 9 }, { date: '2026-07-20', label: 'Jul 20', processed: 56, sent_for_review: 7 },
        { date: '2026-07-21', label: 'Jul 21', processed: 48, sent_for_review: 6 },
      ],
      method: 'Stored document and review events.',
    },
    exception_breakdown: {
      total: 36,
      categories: [
        { id: 'vendor_invoice', label: 'PO / Vendor', count: 12, percentage: 33, color: '#2563eb', href: '/exceptions?category=vendor_invoice' },
        { id: 'tax_amount', label: 'Tax / Amount', count: 8, percentage: 22, color: '#f59e0b', href: '/exceptions?category=tax_amount' },
        { id: 'duplicate', label: 'Duplicate', count: 7, percentage: 19, color: '#7c3aed', href: '/exceptions?category=duplicate' },
        { id: 'dates_details', label: 'Receipt / Docs', count: 5, percentage: 14, color: '#0f8b94', href: '/exceptions?category=dates_details' },
        { id: 'other', label: 'Other', count: 4, percentage: 11, color: '#94a3b8', href: '/exceptions?category=other' },
      ],
    },
    pipeline: { items: [
      { id: 'uploaded', label: 'Uploaded', count: 48, href: '/invoices' }, { id: 'reading', label: 'Reading', count: 3, href: '/invoices?status=processing' },
      { id: 'review', label: 'Waiting for review', count: 24, href: '/review-queue' }, { id: 'approved', label: 'Approved', count: 31, href: '/invoices?status=approved' },
      { id: 'exported', label: 'Exported', count: 19, href: '/exports?status=exported' },
    ], excluded_count: 2, note: 'Two rejected invoices are outside the main processing pipeline.' },
    recent_decisions: [
      { id: 'decision-1', document_id: 'doc-acme-approved', title: 'Invoice approved', invoice: 'INV-2026-04570', vendor: 'Acme Logistics', actor: 'Alex Davis', occurred_at: '2026-07-21T03:12:00Z', tone: 'success', href: '/review/doc-acme-approved' },
      { id: 'decision-2', document_id: 'doc-northstar-correction', title: 'Correction requested', invoice: 'INV-2026-04571', vendor: 'Northstar Office', actor: 'James Smith', occurred_at: '2026-07-21T02:57:00Z', tone: 'danger', href: '/review/doc-northstar-correction' },
      { id: 'decision-3', document_id: 'doc-meridian', title: 'Ready for review', invoice: 'INV-2026-04569', vendor: 'Meridian Freight', actor: 'Kelly Morgan', occurred_at: '2026-07-21T02:15:00Z', tone: 'info', href: '/review/doc-meridian' },
      { id: 'decision-4', document_id: 'doc-northstar-exported', title: 'Export completed', invoice: 'INV-2026-04574', vendor: 'Northstar Office', actor: 'Alex Davis', occurred_at: '2026-07-21T01:15:00Z', tone: 'success', href: '/exports?status=exported' },
    ],
    capabilities: { export_access: true, due_policy: true, sla_policy: false, historical_issue_snapshots: true },
  }
}

function invoiceListFixture(): InvoiceListResponse {
  return {
    items: invoices, page: 1, page_size: 10, total: 126, total_pages: 13,
    summary: { all: 126, waiting_review: 24, needs_correction: 16, approved: 67, exported: 19 },
    insights: { flagged: 8, duplicates_suspected: 3, tax_amount_issues: 2 },
  }
}

function reviewFixture(): ReviewWorklist {
  return { items: reviewItems, page: 1, page_size: 10, total: 24, total_pages: 3, summary: { in_queue: 24, high_risk: 8, invoice_due_today: 3, average_review_seconds: 360 } }
}

function exceptionsFixture(): ExceptionListResponse {
  return {
    items: exceptionItems, page: 1, page_size: 10, total: 36, total_pages: 5,
    summary: {
      open_exceptions: 36, high_risk: 8, warning_issues: 28, invoices_affected: 31,
      categories: { vendor_invoice: 12, tax_amount: 8, duplicate: 7, dates_details: 5, other: 4 },
      top_issues: [
        { label: 'PO number missing', category: 'vendor_invoice', count: 12 },
        { label: 'Receipt required', category: 'dates_details', count: 7 },
        { label: 'Tax amount mismatch', category: 'tax_amount', count: 4 },
      ],
    },
    assignee_options: ['James Smith', 'Alex Davis', 'Kelly Morgan'],
    capabilities: { resolved_history: false, due_policy: false, validated_resolution_only: true },
  }
}

function exportFixture(): ExportWorkspaceResponse {
  return {
    capabilities: { destinations: [{ id: 'csv', label: 'CSV download', formats: ['csv'], mode: 'download' }], scheduling: false, drafts: true, retry: true, configured_provider: 'Local CSV', destination_available: true },
    summary: {
      ready: { count: 12, amount: '45320.75', currency: 'USD' }, in_batch: { count: 4, amount: '7235.40', currency: 'USD' },
      exported: { count: 19, amount: '98450.10', currency: 'USD' }, blocked: { count: 2, amount: '4835.20', currency: 'USD' },
    },
    items: exportItems, page: 1, page_size: 10, total: 12, total_pages: 2,
    filters: { vendors: ['Acme Logistics', 'Northstar Office', 'Meridian Freight', 'Greenline Supply'], currencies: ['USD'], approvers: ['James Smith', 'Alex Davis'] },
    batch: activeBatch, recent_runs: recentRuns,
  }
}

function evaluationFixture(): EvaluationDashboard {
  const runDates = ['2026-05-16', '2026-05-30', '2026-06-13', '2026-06-26', '2026-07-03', '2026-07-10', '2026-07-18']
  const runs = runDates.map((date, index) => ({ id: `eval-${index + 1}`, label: `Invoice scenarios v1 / run ${index + 1}`, dataset_id: 'invoice-scenarios', dataset_version: 'v1', dataset_class: 'synthetic', split: 'test', provider: 'openai', source: 'evaluation_harness', source_document: null, observed_at: `${date}T03:00:00Z`, documents: 20, fields_matched: index === 6 ? 160 : 151 + index, fields_total: 160, field_match: [0.964, 0.96, 0.968, 0.974, 0.973, 0.972, 1][index], validation_match: [0.951, 0.95, 0.954, 0.96, 0.961, 0.966, 1][index], document_exact_match: index === 6 ? 1 : 0.9, approval_blocker_accuracy: index === 6 ? 1 : 0.95, provider_errors: 0, duration_seconds: index === 6 ? 24 : 22 + index, duration_kind: 'wall_clock' as const, provider_calls: 20, estimated_cost_usd: index === 6 ? 0.08 : 0.07, cost_status: 'estimated', cost_claim: 'Estimated from recorded provider usage.', passed: true, verdict_available: true, by_field: { vendor_name: 1, invoice_number: 1, invoice_date: 1, due_date: 1, total: index === 6 ? 1 : 0.99, tax: 0.95, currency: 1 }, failure_taxonomy: {}, limitations: ['Results are from labeled synthetic invoice documents.', 'Small sample size; use for directional engineering evidence.', 'English invoices only.', 'No customer validation has been performed.'], is_current: index === 6 }))
  const selected = runs[6]
  return {
    gates: { field_match: 0.95, validation_match: 0.95, regression_tolerance_pp: 1 },
    preflight: { dataset_id: 'invoice-scenarios', dataset_version: 'v1', dataset_label: 'Synthetic invoice scenarios', available_documents: 20, documents: 20, limited: false, provider_calls_estimate: 20, estimated_cost_usd: 0.08, cost_note: 'List-price estimate before execution.', runnable: true, provider: 'OpenAI extraction provider' },
    runs: runs.map((run) => ({ id: run.id, label: run.label, dataset_id: run.dataset_id, split: run.split, observed_at: run.observed_at, passed: run.passed, verdict_available: run.verdict_available, current: run.is_current })),
    selected_run: selected,
    trend: runs.map((run) => ({ id: run.id, observed_at: run.observed_at, field_match: run.field_match, validation_match: run.validation_match, documents: run.documents, provider_errors: 0, estimated_cost_usd: run.estimated_cost_usd, selected: run.is_current })),
    regression: { comparison_run_id: 'eval-4', comparison_observed_at: '2026-06-26T03:00:00Z', tolerance_pp: 1, comparable_fields: 7, improved: 3, stable: 4, regressed: 0, new_fields: 0, excluded_fields: 0, new_failures: 0 },
    fields: [
      ['vendor_name', 'Vendor', 1, 1, 0, 'stable'], ['invoice_number', 'Invoice number', 1, 0.99, 1, 'improved'], ['invoice_date', 'Invoice date', 1, 0.98, 2, 'improved'],
      ['due_date', 'Due date', 1, 0.98, 2, 'improved'], ['total', 'Total amount', 1, 0.99, 1, 'stable'], ['tax', 'Tax', 0.95, 0.96, -1, 'stable'], ['currency', 'Currency', 1, 1, 0, 'stable'],
    ].map(([field, label, current, previous, delta, status]) => ({ field: String(field), label: String(label), current: Number(current), previous: Number(previous), delta_pp: Number(delta), status: status as 'improved' | 'stable', current_matches: Math.round(Number(current) * 20), current_denominator: 20, previous_matches: Math.round(Number(previous) * 20), previous_denominator: 20 })),
    scenario_coverage: {
      dataset_id: 'invoice-scenarios', dataset_version: 'v1', claim_boundary: 'Synthetic labeled evidence only; this is not production accuracy.', included_in_selected_run: true,
      groups: [
        ['clean', 'Clean invoices', 5, 5], ['missing', 'Missing fields', 4, 5], ['totals', 'Total mismatches', 3, 5], ['duplicates', 'Duplicates', 2, 5], ['scans', 'Low-quality scans', 3, 5], ['multipage', 'Multi-page / rotated', 3, 5],
      ].map(([id, label, current, target]) => ({ id: String(id), label: String(label), current: Number(current), target: Number(target), coverage: Number(current) / Number(target), remaining: Number(target) - Number(current), case_ids: Array.from({ length: Number(current) }, (_, index) => `${id}-${index + 1}`) })),
    },
    attempts: [{ id: 'attempt-current', status: 'succeeded', dataset_id: 'invoice-scenarios', dataset_version: 'v1', documents_requested: 20, documents_processed: 20, provider_calls: 20, run_id: 'eval-7', error_code: null, error_message: null, requested_by: 'James Smith', started_at: '2026-07-18T03:00:00Z', completed_at: '2026-07-18T03:00:24Z' }],
  }
}

function systemFixture(): SystemDashboard {
  return {
    observed_at: observedAt, freshness: { state: 'current', label: 'Observed one minute ago' },
    overall: { status: 'degraded', title: 'Operational with one degraded service', detail: 'Invoice upload, reading, extraction, review, and storage are healthy. CSV export needs attention.' },
    kpis: { processing_now: 3, waiting: 5, completed_today: 48, needs_attention: 1 },
    services: [
      ['uploads', 'Uploads', 'Built-in upload service', 'operational', '142 files uploaded', null, 'Invoice upload remains available.'],
      ['invoice_reading', 'Invoice reading', 'Mistral OCR', 'operational', '138 documents read', null, 'PDF reading remains available.'],
      ['data_extraction', 'Data extraction', 'OpenAI', 'operational', '128 invoices extracted', null, 'Structured extraction remains available.'],
      ['document_storage', 'Document storage', 'Local workspace storage', 'operational', '98.7% capacity available', null, 'Stored invoice files remain available.'],
      ['accounting_export', 'Accounting export', 'Local CSV', 'degraded', 'Last attempt timed out', 'New export execution is temporarily affected.', 'Upload, review, and previous export downloads remain available.'],
    ].map(([id, name, provider, status, activity, affected, unaffected]) => ({ id: String(id), name: String(name), provider: String(provider), status: status as 'operational' | 'degraded', uptime: null, uptime_label: 'Not enough history', observed_at: '2026-07-21T03:14:00Z', activity: String(activity), evidence: `${name} returned a sanitized ${status} observation.`, affected_capability: affected ? String(affected) : null, unaffected_capability: String(unaffected) })),
    alerts: [{ id: 'alert-export', kind: 'service', target_id: 'accounting_export', severity: 'warning', title: 'Accounting export degraded', detail: 'Last attempt timed out. Review the service evidence before retrying.' }],
    flow: { window_label: 'Today', denominator: 'Percentages compare each stage with the uploaded cohort.', stages: [
      { id: 'uploaded', label: 'Upload received', count: 52, previous_count: null, conversion_percent: 100 },
      { id: 'pdf_read', label: 'PDF read', count: 51, previous_count: 52, conversion_percent: 98 },
      { id: 'extracted', label: 'Data extracted', count: 48, previous_count: 51, conversion_percent: 94 },
      { id: 'validated', label: 'Checks completed', count: 48, previous_count: 48, conversion_percent: 100 },
      { id: 'export_attempted', label: 'Export attempted', count: 47, previous_count: 48, conversion_percent: 98 },
      { id: 'export_succeeded', label: 'Export succeeded', count: 46, previous_count: 47, conversion_percent: 98 },
    ] },
    recent_jobs: [
      ['job-1', 'doc-acme', 'INV-2026-04567', 'Reading PDF', 'succeeded', 12000, 1, false, null],
      ['job-2', 'doc-northstar', 'INV-2026-04568', 'Extracting data', 'running', null, 1, false, null],
      ['job-3', 'doc-meridian', 'INV-2026-04569', 'Validating invoice', 'queued', null, 0, false, null],
      ['job-4', 'doc-greenline-approved', 'INV-2026-04573', 'Preparing export', 'succeeded', 18000, 1, false, null],
      ['job-5', 'doc-northstar-exported', 'INV-2026-04574', 'Preparing export', 'failed', 62000, 2, true, 'The CSV file could not be finalized.'],
    ].map(([id, documentId, invoice, stage, status, duration, attempts, retryable, failure], index) => ({ id: String(id), document_id: String(documentId), invoice: String(invoice), filename: `${String(invoice).toLowerCase()}.pdf`, stage: String(stage), status: status as 'succeeded' | 'running' | 'queued' | 'failed', started_at: `2026-07-21T0${3 - Math.min(index, 2)}:${String(14 - index * 2).padStart(2, '0')}:00Z`, finished_at: status === 'running' || status === 'queued' ? null : '2026-07-21T03:14:18Z', duration_ms: duration == null ? null : Number(duration), attempt_count: Number(attempts), retryable: Boolean(retryable), failure_summary: failure ? String(failure) : null })),
    integrations: [
      { id: 'invoice_reading', name: 'Document reader', provider: 'Mistral OCR', status: 'operational', observed_at: '2026-07-21T03:14:00Z', evidence: 'Latest observed request succeeded.' },
      { id: 'data_extraction', name: 'Data extractor', provider: 'OpenAI', status: 'operational', observed_at: '2026-07-21T03:14:00Z', evidence: 'Latest observed extraction succeeded.' },
      { id: 'document_storage', name: 'File storage', provider: 'Local workspace storage', status: 'operational', observed_at: '2026-07-21T03:14:00Z', evidence: 'Storage is writable.' },
      { id: 'accounting_export', name: 'Accounting export', provider: 'Local CSV', status: 'degraded', observed_at: '2026-07-21T03:14:00Z', evidence: 'Latest export attempt failed safely.' },
    ],
    audit: [
      { id: 'audit-1', timestamp: '2026-07-21T03:12:00Z', actor: 'James Smith', action: 'Invoice approved', target: 'INV-2026-04570', result: 'success' },
      { id: 'audit-2', timestamp: '2026-07-21T02:57:00Z', actor: 'Alex Davis', action: 'Correction requested', target: 'INV-2026-04571', result: 'recorded' },
      { id: 'audit-3', timestamp: '2026-07-21T02:55:08Z', actor: 'James Smith', action: 'Export completed', target: 'invoices-2026-07-21.csv', result: 'success' },
    ],
    maintenance: { scheduled: false, title: 'No maintenance scheduled', detail: 'All application components are up to date.' },
  }
}

export async function installPortfolioApi(page: Page, initialRole: PortfolioRole = 'administrator') {
  let role = initialRole
  let cleanApproved = false
  await page.route('**/*', async (route) => {
    const request = route.request()
    const { pathname } = new URL(request.url())
    if (pathname === '/auth/session') {
      const actor = role === 'administrator' ? 'James Smith' : role === 'reviewer' ? 'Alex Davis' : 'Invoice Uploader'
      return route.fulfill({ json: { authenticated: true, actor, user_id: `portfolio-${role}`, workspace_id: 'portfolio', role, is_admin: role === 'administrator' } })
    }
    if (request.resourceType() === 'document') return route.continue()
    if (pathname === '/backoffice/workspace') return route.fulfill({ json: { workspace_id: 'portfolio', work_items: [], pending_approvals: [], documents: invoices, metrics: {} } })
    if (pathname === '/overview/dashboard') return route.fulfill({ json: overviewFixture() })
    if (pathname === '/invoices') return route.fulfill({ json: invoiceListFixture() })
    if (pathname === '/review/worklist') return route.fulfill({ json: reviewFixture() })
    if (pathname === '/exceptions') return route.fulfill({ json: exceptionsFixture() })
    if (pathname === '/exports/workspace') return route.fulfill({ json: exportFixture() })
    if (pathname === '/evaluation/dashboard') return route.fulfill({ json: evaluationFixture() })
    if (pathname === '/system/dashboard') return route.fulfill({ json: systemFixture() })
    if (pathname === '/operations/notifications') return route.fulfill({ json: { notifications: [], unread_count: 3 } })
    if (pathname === '/providers/health') return route.fulfill({ json: { overall_status: 'degraded', providers: [] } })
    if (pathname === '/operations/jobs') return route.fulfill({ json: { worker: { status: 'healthy', queued_jobs: 5, failed_jobs: 1, stalled_jobs: 0, evidence: 'Worker heartbeat observed.' }, failed_jobs: [] } })
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
      const workflow: ReviewWorkflow = { current_stage: cleanApproved && invoice?.id === 'doc-acme' ? 'approved' : invoice?.current_stage ?? 'needs_review', current_owner: invoice?.current_owner ?? 'Finance reviewer', waiting_for: invoice?.status === 'needs_review' ? 'Reviewer decision' : 'Nothing', next_action: invoice?.has_validation_errors ? 'Request correction' : 'Review invoice', attention_reason: invoice?.validation_codes[0] ? findingLabels[invoice.validation_codes[0]] : null, work_item: { assignee: invoice?.current_owner } }
      return route.fulfill({ json: workflow })
    }
    const contentMatch = pathname.match(/^\/documents\/([^/]+)\/content$/)
    if (contentMatch) return route.fulfill({ contentType: 'application/pdf', body: contentMatch[1].includes('meridian') ? duplicatePdf : cleanPdf })
    const documentMatch = pathname.match(/^\/documents\/([^/]+)$/)
    if (documentMatch) {
      const invoice = invoiceById.get(documentMatch[1])
      if (invoice) return route.fulfill({ json: detailFor(invoice, cleanApproved && invoice.id === 'doc-acme') })
    }
    if (pathname === '/review/doc-acme/approve' && request.method() === 'POST') {
      cleanApproved = true
      return route.fulfill({ json: { document: { id: 'doc-acme', status: 'approved', updated_at: observedAt }, review_task: { status: 'approved', reviewer_notes: '', reviewed_by: 'James Smith', reviewed_at: observedAt }, decision: { status: 'approved', actor: 'James Smith', recorded_at: observedAt, note: '', audit_event_count: 3, export_eligibility: 'eligible' } } })
    }
    if (pathname.startsWith('/review/') && pathname.endsWith('/save') && request.method() === 'POST') return route.fulfill({ json: { saved: true } })
    if (pathname.startsWith('/invoices/') && pathname.endsWith('/request-correction') && request.method() === 'POST') return route.fulfill({ json: { status: 'correction_requested' } })
    if (pathname.startsWith('/invoices/') && pathname.endsWith('/draft') && request.method() === 'POST') return route.fulfill({ json: { status: 'needs_review' } })
    return route.continue()
  })

  return {
    setRole(nextRole: PortfolioRole) { role = nextRole },
    setApproved(value: boolean) { cleanApproved = value },
  }
}
