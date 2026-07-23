import { describe, expect, it } from 'vitest'
import type { ReviewQueueItem } from '../review/types'
import { inboxStateForReviewItem, isDecisionQueueItem, type InboxState } from './selectors'

const baseItem: ReviewQueueItem = {
  id: 'doc-1',
  original_filename: 'invoice.pdf',
  invoice_number: 'INV-001',
  vendor_name: 'Acme Logistics',
  total: '1250.00',
  currency: 'USD',
  invoice_date: '2026-07-20',
  due_date: '2026-07-30',
  owner: 'Reviewer',
  risk: 'low',
  confidence: 0.94,
  finding: 'Review extracted invoice data',
  blocker_count: 0,
  issue_count: 0,
  can_approve: true,
  recommended_action: 'review',
  age_seconds: 600,
  created_at: '2026-07-20T10:00:00Z',
  updated_at: '2026-07-20T10:10:00Z',
}

describe('inbox selectors', () => {
  it('keeps decision-ready and validation-blocked work mutually exclusive', () => {
    const decisionReady = baseItem
    const blocked = {
      ...baseItem,
      id: 'doc-2',
      blocker_count: 1,
      issue_count: 1,
      can_approve: false,
      recommended_action: 'request_correction' as const,
    }

    expect(inboxStateForReviewItem(decisionReady)).toBe('needs-decision')
    expect(inboxStateForReviewItem(blocked)).toBe('blocked')
    expect(isDecisionQueueItem(decisionReady)).toBe(true)
    expect(isDecisionQueueItem(blocked)).toBe(false)

    const states: InboxState[] = ['needs-decision', 'blocked']
    for (const item of [decisionReady, blocked]) {
      expect(states.filter((state) => inboxStateForReviewItem(item) === state)).toHaveLength(1)
    }
  })

  it('treats a server-declared approval restriction as blocked even without a count', () => {
    expect(inboxStateForReviewItem({ ...baseItem, can_approve: false })).toBe('blocked')
  })
})
