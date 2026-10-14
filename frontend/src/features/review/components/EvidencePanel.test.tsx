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
    expect(screen.getByText(/Posting is not enabled/)).toBeInTheDocument()
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
})
