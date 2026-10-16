import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { EvidencePanel } from './EvidencePanel'

vi.mock('../../../api/client', () => ({ api: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const record = {
  current: {
    version: 2,
    actor: 'Reviewer',
    at: '2026-10-14T00:00:00Z',
    reason: 'Checked',
    line_ids: [],
    changes: {},
    fields: {
      total: {
        kind: 'observed',
        raw: '10',
        normalized: '10',
        effective: '10',
        page: 3,
        excerpt: 'Total 10',
      },
    },
  },
  history: [],
  needs_capture: false,
  capabilities: { review: true, approve: false },
  snapshot_status: null,
}
function mount(data: unknown) {
  vi.mocked(api).mockResolvedValue(data)
  const showPage = vi.fn()
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <EvidencePanel documentId="doc-1" showPage={showPage} />
    </QueryClientProvider>,
  )
  return showPage
}
describe('AP evidence review', () => {
  it('opens the exact source page and keeps posting disabled', async () => {
    const showPage = mount(record)
    fireEvent.click(await screen.findByRole('button', { name: 'Page 3' }))
    expect(showPage).toHaveBeenCalledWith(3)
    expect(screen.getByText(/ERP submit approval are separate decisions/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Approve this evidence snapshot' }),
    ).not.toBeInTheDocument()
  })
  it('disables approval for a stale snapshot', async () => {
    mount({
      ...record,
      capabilities: { review: false, approve: true },
      snapshot_status: {
        status: 'stale',
        posting_ready: false,
        snapshot: {
          id: 's',
          payload_hash: 'h',
          blockers: [],
          inputs: { sources: { po: [], receipt: [] } },
        },
      },
    })
    expect(
      await screen.findByRole('button', { name: 'Approve this evidence snapshot' }),
    ).toBeDisabled()
    expect(
      screen.queryByRole('button', { name: 'Capture current invoice' }),
    ).not.toBeInTheDocument()
  })
  it('shows separate price and quantity exceptions with a next action', async () => {
    mount({
      ...record,
      capabilities: { review: false, approve: true },
      match_status: {
        status: 'hold',
        match: {
          id: 'match-1',
          basis_hash: 'hash',
          recommendation: 'hold',
          policy: {
            version: 1,
            record: { mode: 'received', effective_from: '2026-01-01T00:00:00Z' },
          },
          lines: [
            {
              line_id: 'l1',
              source_ref: 'PO1:p1',
              expected_price: '50',
              actual_price: '55',
              price_delta: '5',
              price_threshold: '0',
              ordered: '100',
              received: '70',
              billed: '0',
              reserved: '0',
              available: '70',
              invoice_quantity: '100',
            },
          ],
          issues: [
            { code: 'price_variance', line_id: 'l1', facts: { delta: '5' } },
            {
              code: 'quantity_exceeds_available',
              line_id: null,
              facts: { requested: '100', available: '70' },
            },
          ],
        },
      },
    })
    expect(await screen.findByText('price variance')).toBeInTheDocument()
    expect(screen.getByText('quantity exceeds available')).toBeInTheDocument()
    expect(screen.getByText(/Check accepted receipts and earlier billings/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Approve match and reserve quantity' }),
    ).toBeDisabled()
  })
})
