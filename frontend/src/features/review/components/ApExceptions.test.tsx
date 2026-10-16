import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { ApExceptionDecisions, ApExceptionInbox } from './ApExceptions'

vi.mock('../../../api/client', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())

const item = {
  id: 'case-1',
  version: 2,
  document_id: 'doc-1',
  code: 'duplicate_confirmed',
  state: 'open',
  owner: null,
  reason: 'Detected by current match',
  evidence_refs: [],
  authorizer: null,
  match_id: 'match-1',
  created_at: '2026-10-14T00:00:00Z',
  at: '2026-10-14T00:00:00Z',
}

function mount(component: React.ReactNode) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>{component}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AP exception workflow', () => {
  it('shows prioritized issue, age, owner, next action and invoice link', async () => {
    vi.mocked(api).mockResolvedValue({ items: [item] })
    mount(<ApExceptionInbox />)
    expect(await screen.findByText('duplicate confirmed · open')).toBeInTheDocument()
    expect(screen.getByText('Unassigned')).toBeInTheDocument()
    expect(screen.getByText(/Compare both source invoices/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review invoice' })).toHaveAttribute(
      'href',
      '/review/doc-1',
    )
  })

  it('records an evidence request without offering a confirmed-duplicate waiver to a reviewer', async () => {
    vi.mocked(api).mockImplementation(async (path) =>
      path.startsWith('/ap/exceptions?') ? { items: [item] } : { ...item, state: 'needs_info' },
    )
    mount(<ApExceptionDecisions documentId="doc-1" canReview isAdmin={false} matchId="match-1" />)
    fireEvent.click(await screen.findByText('Record action'))
    expect(
      screen.queryByRole('button', { name: 'Authorize policy waiver' }),
    ).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'Reviewer' } })
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Need the original invoice' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Request evidence' }))
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/ap/exceptions/case-1',
        expect.objectContaining({ method: 'PUT' }),
      ),
    )
    const payload = JSON.parse(
      String(
        vi.mocked(api).mock.calls.find(([path]) => path === '/ap/exceptions/case-1')?.[1]?.body,
      ),
    )
    expect(payload).toMatchObject({
      expected_version: 2,
      expected_match_id: 'match-1',
      state: 'needs_info',
      owner: 'Reviewer',
    })
  })

  it('lets an approver reject with a reason and source reference without offering a waiver', async () => {
    vi.mocked(api).mockImplementation(async (path) =>
      path.startsWith('/ap/exceptions?') ? { items: [item] } : { ...item, state: 'rejected' },
    )
    mount(
      <ApExceptionDecisions
        documentId="doc-1"
        canReview={false}
        canReject
        isAdmin={false}
        matchId="match-1"
      />,
    )
    fireEvent.click(await screen.findByText('Record action'))
    expect(
      screen.queryByRole('button', { name: 'Authorize policy waiver' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject invoice' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'AP Approver' } })
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Confirmed duplicate of the original invoice' },
    })
    fireEvent.change(screen.getByLabelText('Source or evidence reference'), {
      target: { value: 'invoice:original' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reject invoice' }))
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        '/ap/exceptions/case-1',
        expect.objectContaining({ method: 'PUT' }),
      ),
    )
    const payload = JSON.parse(
      String(
        vi.mocked(api).mock.calls.find(([path]) => path === '/ap/exceptions/case-1')?.[1]?.body,
      ),
    )
    expect(payload).toMatchObject({ state: 'rejected', evidence_refs: ['invoice:original'] })
  })
})
