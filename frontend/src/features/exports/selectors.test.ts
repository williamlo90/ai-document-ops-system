import { describe, expect, it } from 'vitest'
import type { ExportInvoiceItem, ExportWorkspaceResponse } from './types'
import { belongsToExportView, exportViewCount, exportViews, isExportReady } from './selectors'

function exportItem(status: ExportInvoiceItem['status']): ExportInvoiceItem {
  return {
    id: `doc-${status}`,
    invoice_label: `INV-${status}`,
    filename: `${status}.pdf`,
    vendor_name: 'Acme Logistics',
    approved_by: status === 'blocked' ? null : 'Reviewer',
    approved_at: status === 'blocked' ? null : '2026-07-20T10:00:00Z',
    total: '1250.00',
    currency: 'USD',
    status,
    issue: status === 'blocked' ? 'Waiting for approval' : null,
    batch_id: ['in_batch', 'drafts', 'exported'].includes(status) ? `batch-${status}` : null,
    updated_at: '2026-07-20T10:10:00Z',
  }
}

describe('export selectors', () => {
  it('assigns every invoice to exactly one export view', () => {
    for (const status of exportViews) {
      const item = exportItem(status)
      expect(exportViews.filter((view) => belongsToExportView(item, view))).toEqual([status])
    }
  })

  it('allows selection only for genuinely ready invoices', () => {
    expect(isExportReady(exportItem('ready'))).toBe(true)
    for (const status of ['blocked', 'in_batch', 'exported', 'drafts'] as const) {
      expect(isExportReady(exportItem(status))).toBe(false)
    }
  })

  it('uses the same server summary that labels non-draft tabs', () => {
    const data: ExportWorkspaceResponse = {
      capabilities: {
        destinations: [],
        scheduling: false,
        drafts: true,
        retry: true,
        configured_provider: 'csv_download',
        destination_available: true,
      },
      summary: {
        ready: { count: 2, amount: '2500.00', currency: 'USD' },
        in_batch: { count: 1, amount: '1250.00', currency: 'USD' },
        exported: { count: 1, amount: '1250.00', currency: 'USD' },
        blocked: { count: 3, amount: '3750.00', currency: 'USD' },
      },
      items: [],
      page: 1,
      page_size: 10,
      total: 2,
      total_pages: 1,
      filters: { vendors: [], currencies: [], approvers: [] },
      batch: null,
      recent_runs: [],
    }

    expect(exportViewCount(data, 'ready', 'ready')).toBe(2)
    expect(exportViewCount(data, 'blocked', 'ready')).toBe(3)
    expect(exportViewCount(data, 'drafts', 'ready')).toBeNull()
    expect(exportViewCount({ ...data, total: 4 }, 'drafts', 'drafts')).toBe(4)
  })
})
