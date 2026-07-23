import { describe, expect, it } from 'vitest'
import type { InvoiceItem } from './types'
import {
  belongsToInvoiceLifecycle,
  invoiceLifecycleFilters,
  invoiceLifecycleFor,
} from './selectors'

function invoice(businessStatus: string): InvoiceItem {
  return {
    id: `doc-${businessStatus}`,
    original_filename: `${businessStatus}.pdf`,
    submitted_by: 'Uploader',
    status: businessStatus === 'needs_correction' ? 'needs_review' : businessStatus,
    business_status: businessStatus,
    current_stage: businessStatus,
    current_owner: 'Finance reviewer',
    vendor_name: 'Acme Logistics',
    invoice_number: `INV-${businessStatus}`,
    invoice_date: '2026-07-20',
    due_date: '2026-07-30',
    total: '1250.00',
    currency: 'USD',
    created_at: '2026-07-20T10:00:00Z',
    updated_at: '2026-07-20T10:10:00Z',
    validation_issue_count: businessStatus === 'needs_correction' ? 1 : 0,
    validation_error_count: businessStatus === 'needs_correction' ? 1 : 0,
    validation_codes: businessStatus === 'needs_correction' ? ['missing_field'] : [],
    has_validation_errors: businessStatus === 'needs_correction',
    export_state:
      businessStatus === 'approved'
        ? 'eligible'
        : businessStatus === 'exported'
          ? 'exported'
          : 'not_eligible',
    work_item_id: null,
    correction_reason: businessStatus === 'needs_correction' ? 'Fix the missing field.' : null,
  }
}

describe('invoice lifecycle selectors', () => {
  it('uses the durable business status instead of the raw processing status', () => {
    const correction = invoice('needs_correction')
    expect(correction.status).toBe('needs_review')
    expect(invoiceLifecycleFor(correction)).toBe('needs_correction')
    expect(belongsToInvoiceLifecycle(correction, 'needs_correction')).toBe(true)
    expect(belongsToInvoiceLifecycle(correction, 'needs_review')).toBe(false)
  })

  it('assigns each durable lifecycle to one named tab plus All', () => {
    for (const status of ['needs_review', 'needs_correction', 'approved', 'exported']) {
      const item = invoice(status)
      const namedMatches = invoiceLifecycleFilters
        .filter((filter) => filter !== '')
        .filter((filter) => belongsToInvoiceLifecycle(item, filter))
      expect(namedMatches).toEqual([status])
      expect(belongsToInvoiceLifecycle(item, '')).toBe(true)
    }
  })
})
