import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { api } from '../../../api/client'
import { Button, Panel } from '../../../shared/ui'

export type ApCase = {
  id: string
  version: number
  document_id: string
  code: string
  state: string
  owner: string | null
  reason: string
  evidence_refs: string[]
  authorizer: string | null
  match_id: string
  created_at: string
  at: string
}

type CaseList = { items: ApCase[] }

function nextAction(code: string) {
  if (code === 'duplicate_confirmed') return 'Compare both source invoices and correct the duplicate record.'
  if (code === 'duplicate_candidate') return 'Compare invoice numbers and source documents.'
  if (code === 'price_variance') return 'Check the invoice or PO price against source evidence.'
  if (code.includes('receipt') || code.includes('quantity')) return 'Check accepted receipts and prior billings.'
  if (code.includes('evidence')) return 'Verify the source evidence and prepare a current snapshot.'
  return 'Correct the source data, then reassess the match.'
}

export function ApExceptionInbox() {
  const cases = useQuery({
    queryKey: ['ap-exceptions'],
    queryFn: () => api<CaseList>('/ap/exceptions'),
    refetchInterval: 10_000,
  })
  const active = (cases.data?.items ?? []).filter((item) => !['resolved', 'superseded', 'waived'].includes(item.state))
  return (
    <Panel>
      <h2>Purchasing match exceptions ({active.length})</h2>
      <p>Open issues stay blocking until the source is corrected and a new match is assessed, or an allowed waiver is authorized.</p>
      {cases.error && <p role="alert">{cases.error.message}</p>}
      {cases.isLoading && <p>Loading match exceptions…</p>}
      {active.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead><tr><th>Issue</th><th>Waiting since</th><th>Owner</th><th>Next action</th><th>Invoice</th></tr></thead>
            <tbody>{active.map((item) => (
              <tr key={item.id}>
                <td>{item.code.replaceAll('_', ' ')} · {item.state.replaceAll('_', ' ')}</td>
                <td>{new Date(item.created_at).toLocaleDateString()}</td>
                <td>{item.owner ?? 'Unassigned'}</td>
                <td>{nextAction(item.code)}</td>
                <td><Link to={`/review/${item.document_id}`}>Review invoice</Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {!cases.isLoading && !cases.error && active.length === 0 && <p>No active purchasing match exceptions.</p>}
    </Panel>
  )
}

export function ApExceptionDecisions({ documentId, canReview, isAdmin, matchId }: {
  documentId: string
  canReview: boolean
  isAdmin: boolean
  matchId: string | null
}) {
  const client = useQueryClient()
  const [owner, setOwner] = useState('')
  const [reason, setReason] = useState('')
  const [reference, setReference] = useState('')
  const cases = useQuery({
    queryKey: ['ap-exceptions', documentId],
    queryFn: () => api<CaseList>(`/ap/exceptions?document_id=${documentId}`),
  })
  const decide = useMutation({
    mutationFn: ({ item, state }: { item: ApCase; state: string }) => api(`/ap/exceptions/${item.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        expected_version: item.version,
        expected_match_id: item.match_id,
        state,
        owner: owner.trim() || item.owner || '',
        reason: reason.trim(),
        evidence_refs: reference.trim() ? [reference.trim()] : [],
      }),
    }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['ap-exceptions'] })
      void client.invalidateQueries({ queryKey: ['ap-evidence', documentId] })
    },
  })
  const active = (cases.data?.items ?? []).filter((item) => item.match_id === matchId && !['resolved', 'superseded'].includes(item.state))
  if (!matchId) return null
  return (
    <section>
      <h3>Exception resolution</h3>
      {cases.error && <p role="alert">{cases.error.message}</p>}
      {active.map((item) => (
        <article key={item.id}>
          <strong>{item.code.replaceAll('_', ' ')} · {item.state.replaceAll('_', ' ')}</strong>
          <p>Owner: {item.owner ?? 'Unassigned'} · {item.reason}</p>
          {item.authorizer && <p>Authorized by {item.authorizer}</p>}
          {(canReview || isAdmin) && (
            <details>
              <summary>Record action</summary>
              <label>Owner <input value={owner} onChange={(event) => setOwner(event.target.value)} /></label>
              <label>Reason <input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
              <label>Source or evidence reference <input value={reference} onChange={(event) => setReference(event.target.value)} /></label>
              <div>
                {(['needs_info', 'resolved', ...(isAdmin ? ['waived'] : [])] as const).map((state) => (
                  <Button key={state} disabled={decide.isPending || !(owner.trim() || item.owner) || reason.trim().length < 10 || (state !== 'needs_info' && !reference.trim())}
                    onClick={() => decide.mutate({ item, state })}>
                    {state === 'needs_info' ? 'Request evidence' : state === 'resolved' ? 'Mark resolved' : 'Authorize policy waiver'}
                  </Button>
                ))}
              </div>
            </details>
          )}
        </article>
      ))}
      {decide.error && <p role="alert">{decide.error.message}</p>}
    </section>
  )
}
