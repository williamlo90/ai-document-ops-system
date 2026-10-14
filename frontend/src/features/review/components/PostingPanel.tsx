import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../api/client'
import { Button } from '../../../shared/ui'

type Operation = {
  id: string
  state: string
  target: string | null
  verification_hash?: string
  error_code?: string
  error_detail?: string
  posted_verified?: boolean
  retryable?: boolean
  receipt_allocations?: Record<string, string>
}
type SubmitApproval = { approval_hash: string; actor: string; reason: string }
type PostingStatus = {
  match_status: string
  sandbox_enabled: boolean
  profile_version: number | null
  draft: Operation | null
  submit_approval: SubmitApproval | null
  submit: Operation | null
  posted_verified: boolean
}

export function PostingPanel({ matchId, basisHash, canApprove, isAdmin, lineIds }: {
  matchId: string
  basisHash: string
  canApprove: boolean
  isAdmin: boolean
  lineIds: string[]
}) {
  const client = useQueryClient()
  const [reason, setReason] = useState('')
  const [receiptAllocations, setReceiptAllocations] = useState<Record<string, string>>({})
  const query = useQuery({
    queryKey: ['ap-posting', matchId],
    queryFn: () => api<PostingStatus>(`/ap/posting/${matchId}`),
    refetchInterval: 10_000,
  })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['ap-posting', matchId] })
    void client.invalidateQueries({ queryKey: ['ap-evidence'] })
  }
  const create = useMutation({
    mutationFn: () => api(`/ap/posting/${matchId}/draft`, { method: 'POST', body: JSON.stringify({
      match_id: matchId, expected_basis_hash: basisHash,
      receipt_allocations: query.data?.draft?.receipt_allocations ??
        Object.fromEntries(Object.entries(receiptAllocations).filter(([, value]) => value.trim())),
    }) }),
    onSuccess: refresh,
  })
  const approve = useMutation({
    mutationFn: () => api(`/ap/posting/${matchId}/approve-submit`, { method: 'POST', body: JSON.stringify({
      operation_id: query.data?.draft?.id, draft_verification_hash: query.data?.draft?.verification_hash,
      reason,
    }) }),
    onSuccess: refresh,
  })
  const submit = useMutation({
    mutationFn: () => api(`/ap/posting/${matchId}/submit`, { method: 'POST', body: JSON.stringify({
      approval_hash: query.data?.submit_approval?.approval_hash,
    }) }),
    onSuccess: refresh,
  })
  const reconcile = useMutation({
    mutationFn: (kind: 'create' | 'submit') => api(`/ap/posting/${matchId}/reconcile/${kind}`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const confirmAbsent = useMutation({
    mutationFn: () => api(`/ap/posting/${matchId}/confirm-draft-absent`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const data = query.data
  const error = query.error || create.error || approve.error || submit.error || reconcile.error || confirmAbsent.error
  return (
    <section>
      <h3>ERPNext sandbox delivery</h3>
      <p>Draft verification and submit approval are separate. No payment is initiated.</p>
      {query.isLoading && <p>Loading ERP operation status…</p>}
      {error && <p role="alert">{error.message}</p>}
      {data && !data.sandbox_enabled && <p>Sandbox posting is disabled in configuration.</p>}
      {data && !data.profile_version && <p>An administrator must configure a verified ERP posting profile.</p>}
      {data?.draft && <p>Draft: {data.draft.state.replaceAll('_', ' ')} · ERP target {data.draft.target ?? 'unknown'}</p>}
      {data?.draft?.error_code && <p>Draft issue: {data.draft.error_code} {data.draft.error_detail ?? ''}</p>}
      {data?.submit_approval && <p>Submit approved by {data.submit_approval.actor}: {data.submit_approval.reason}</p>}
      {data?.submit && <p>Submit: {data.submit.state.replaceAll('_', ' ')} · ERP target {data.submit.target ?? 'unknown'}</p>}
      {data?.submit?.error_code && <p>Submit issue: {data.submit.error_code} {data.submit.error_detail ?? ''}</p>}
      {data?.posted_verified && <strong>Posted and verified against ERP document and ledger</strong>}
      {canApprove && data?.sandbox_enabled && data.profile_version && data.match_status === 'approved' && !data.draft && (
        <div>
          <p>For a PO line with multiple receipts, choose one accepted receipt line per invoice line.</p>
          {lineIds.map((lineId) => <label key={lineId}>
            Receipt for {lineId} (optional: receipt ID:line ID)
            <input value={receiptAllocations[lineId] ?? ''}
              onChange={(event) => setReceiptAllocations({ ...receiptAllocations, [lineId]: event.target.value })} />
          </label>)}
          <Button disabled={create.isPending} onClick={() => create.mutate()}>Create and verify ERP draft</Button>
        </div>
      )}
      {canApprove && data?.draft?.state === 'confirmed' && !data.submit_approval && (
        <div>
          <label>Independent submit approval reason
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <Button disabled={approve.isPending || reason.trim().length < 10} onClick={() => approve.mutate()}>
            Approve ERP submit separately
          </Button>
        </div>
      )}
      {canApprove && data?.submit_approval && !data.submit && (
        <Button disabled={submit.isPending} onClick={() => submit.mutate()}>Submit approved ERP draft</Button>
      )}
      {canApprove && data?.draft && ['unknown', 'reconciliation_required'].includes(data.draft.state) && (
        <Button disabled={reconcile.isPending} onClick={() => reconcile.mutate('create')}>Reconcile draft outcome</Button>
      )}
      {isAdmin && data?.draft && ['pending', 'unknown'].includes(data.draft.state) && !data.draft.target && (
        <Button disabled={confirmAbsent.isPending} onClick={() => confirmAbsent.mutate()}>
          Confirm draft absent for safe retry
        </Button>
      )}
      {canApprove && data?.draft?.state === 'failed' && data.draft.retryable && (
        <Button disabled={create.isPending} onClick={() => create.mutate()}>Retry draft with same key</Button>
      )}
      {canApprove && data?.submit && ['unknown', 'reconciliation_required'].includes(data.submit.state) && (
        <Button disabled={reconcile.isPending} onClick={() => reconcile.mutate('submit')}>Reconcile submit outcome</Button>
      )}
      {data?.match_status === 'stale' && <p>Source or match changed. Reassess before a new ERP operation.</p>}
    </section>
  )
}
