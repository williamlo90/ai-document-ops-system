import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import { PostingPanel } from './PostingPanel'

vi.mock('../../../api/client', () => ({ api: vi.fn() }))
afterEach(() => vi.clearAllMocks())

const ready = { match_status: 'approved', sandbox_enabled: true, profile_version: 1,
  draft: null, submit_approval: null, submit: null, posted_verified: false }

function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <PostingPanel matchId="match-1" basisHash="basis-hash" canApprove isAdmin={false} lineIds={['line-1']} />
  </QueryClientProvider>)
}

describe('ERP posting decisions', () => {
  it('offers draft creation only for an approved match with an enabled profile', async () => {
    vi.mocked(api).mockImplementation(async (path) => path === '/ap/posting/match-1' ? ready : { id: 'create:match-1' })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Create and verify ERP draft' }))
    await waitFor(() => expect(api).toHaveBeenCalledWith('/ap/posting/match-1/draft', expect.objectContaining({ method: 'POST' })))
    expect(screen.queryByRole('button', { name: 'Submit approved ERP draft' })).not.toBeInTheDocument()
  })

  it('requires an explicit reason for the separate submit approval', async () => {
    vi.mocked(api).mockResolvedValue({ ...ready, draft: { id: 'create:match-1', state: 'confirmed',
      target: 'PINV-1', verification_hash: 'verified-hash' } })
    mount()
    const button = await screen.findByRole('button', { name: 'Approve ERP submit separately' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Independent submit approval reason'), {
      target: { value: 'Verified source and draft' },
    })
    expect(button).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Submit approved ERP draft' })).not.toBeInTheDocument()
  })
})
