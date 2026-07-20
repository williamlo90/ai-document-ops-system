import type { InvoiceItem } from './types'

export function invoiceStatus(value: string): { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'purple' } {
  return ({
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
  } as const)[value] ?? { label: humanize(value), tone: 'neutral' }
}

export function invoiceLabel(invoice: Pick<InvoiceItem, 'invoice_number' | 'id'>): string {
  return invoice.invoice_number || invoice.id.slice(0, 8).toUpperCase()
}

export function formatMoney(value?: string | null, currency?: string | null): string {
  if (value == null || Number.isNaN(Number(value))) return '-'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD', maximumFractionDigits: 2 }).format(Number(value))
  } catch {
    return `${currency || ''} ${Number(value).toLocaleString()}`.trim()
  }
}

export function formatDate(value?: string | null, includeTime = false): string {
  if (!value) return '-'
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, includeTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }).format(date)
}

export function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}
