import type { InvoiceItem } from './types'

export function invoiceLabel(invoice: Pick<InvoiceItem, 'invoice_number' | 'id'>): string {
  return invoice.invoice_number || invoice.id.slice(0, 8).toUpperCase()
}
