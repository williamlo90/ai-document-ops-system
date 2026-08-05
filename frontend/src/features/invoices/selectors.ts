import { humanize } from '../../shared/format'
import type { InvoiceItem, InvoiceListResponse } from './types'

export const invoiceLifecycleFilters = [
  '',
  'needs_review',
  'needs_correction',
  'approved',
  'exported',
] as const

export type InvoiceLifecycleFilter = (typeof invoiceLifecycleFilters)[number]

export function isInvoiceLifecycleFilter(value: string | null): value is InvoiceLifecycleFilter {
  return invoiceLifecycleFilters.includes(value as InvoiceLifecycleFilter)
}

export function invoiceLifecycleFor(item: InvoiceItem): string {
  return item.business_status
}

export function belongsToInvoiceLifecycle(
  item: InvoiceItem,
  filter: InvoiceLifecycleFilter,
): boolean {
  return filter === '' || invoiceLifecycleFor(item) === filter
}

export function invoiceStatus(value: string): {
  label: string
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'purple'
} {
  return (
    (
      {
        uploaded: { label: 'Uploaded', tone: 'neutral' },
        queued: { label: 'Reading', tone: 'info' },
        processing: { label: 'Reading', tone: 'info' },
        needs_review: { label: 'Waiting for review', tone: 'info' },
        needs_correction: { label: 'Needs correction', tone: 'danger' },
        approved: { label: 'Approved', tone: 'success' },
        exported: { label: 'Exported', tone: 'purple' },
        rejected: { label: 'Rejected', tone: 'danger' },
        failed: { label: 'Needs correction', tone: 'danger' },
        cancelled: { label: 'Cancelled', tone: 'neutral' },
      } as const
    )[value] ?? { label: humanize(value), tone: 'neutral' }
  )
}

export function invoiceTabs(summary?: InvoiceListResponse['summary']) {
  return [
    { label: 'All', value: '' as const, count: summary?.all ?? 0 },
    {
      label: 'Needs review',
      value: 'needs_review' as const,
      count: summary?.waiting_review ?? 0,
    },
    {
      label: 'Needs correction',
      value: 'needs_correction' as const,
      count: summary?.needs_correction ?? 0,
    },
    { label: 'Approved', value: 'approved' as const, count: summary?.approved ?? 0 },
    { label: 'Exported', value: 'exported' as const, count: summary?.exported ?? 0 },
  ]
}
