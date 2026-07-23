import type { ExportInvoiceItem, ExportWorkspaceResponse } from './types'

export const exportViews = ['ready', 'in_batch', 'exported', 'blocked', 'drafts'] as const

export type ExportView = (typeof exportViews)[number]

export function isExportView(value: string | null): value is ExportView {
  return exportViews.includes(value as ExportView)
}

export function exportViewForItem(item: ExportInvoiceItem): ExportView {
  return item.status
}

export function isExportReady(item: ExportInvoiceItem): boolean {
  return exportViewForItem(item) === 'ready'
}

export function belongsToExportView(item: ExportInvoiceItem, view: ExportView): boolean {
  return exportViewForItem(item) === view
}

export function exportViewCount(
  data: ExportWorkspaceResponse | undefined,
  view: ExportView,
  active: ExportView,
): number | null {
  if (view === 'drafts') return active === 'drafts' ? (data?.total ?? null) : null
  return data?.summary[view]?.count ?? null
}
