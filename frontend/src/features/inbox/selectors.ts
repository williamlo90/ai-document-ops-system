import type { ExceptionCategory, ExceptionItem } from '../exceptions/types'
import type { ReviewQueueItem } from '../review/types'

export type InboxState = 'needs-decision' | 'blocked'

export const categoryLabels: Record<ExceptionCategory, string> = {
  vendor_invoice: 'Vendor or invoice',
  tax_amount: 'Tax or amount',
  duplicate: 'Duplicate',
  dates_details: 'Dates or details',
  other: 'Other',
}

export function inboxStateForReviewItem(item: ReviewQueueItem): InboxState {
  return item.blocker_count > 0 || !item.can_approve ? 'blocked' : 'needs-decision'
}

export function isDecisionQueueItem(item: ReviewQueueItem): boolean {
  return inboxStateForReviewItem(item) === 'needs-decision'
}

export function isBlockingException(item: ExceptionItem): boolean {
  return item.blocks_approval
}
