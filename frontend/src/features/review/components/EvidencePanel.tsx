import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../../api/client'
import { Button, Panel } from '../../../shared/ui'
import { ApExceptionDecisions } from './ApExceptions'
import { PostingPanel } from './PostingPanel'

type Evidence = {
  kind: string
  raw: string | null
  normalized: string | null
  effective: string | null
  page: number | null
  excerpt: string | null
  reason?: string
  actor?: string
}
type Revision = {
  version: number
  actor: string
  at: string
  reason: string
  fields: Record<string, Evidence>
  line_ids: string[]
  changes: Record<string, { before: Evidence | null; after: Evidence }>
}
type Source = {
  version: number
  synced_at: string
  record: {
    source_id: string
    source_version: string
    status: string
    supplier_id: string
    source_updated_at: string
    lines: { source_line_id: string; item_id: string; uom: string; quantity: string }[]
  }
}
type Snapshot = {
  id: string
  payload_hash: string
  blockers: string[]
  inputs: { sources: { po: Source[]; receipt: Source[] } }
}
type Status = { snapshot: Snapshot; status: string; posting_ready: boolean }
type MatchIssue = { code: string; line_id: string | null; facts: Record<string, string | number | boolean> }
type MatchLine = {
  line_id: string
  source_ref: string
  expected_price: string
  actual_price: string
  price_delta: string
  price_threshold: string
  ordered: string
  received: string
  billed: string
  reserved: string
  available: string
  invoice_quantity: string
}
type MatchStatus = {
  status: string
  match: {
    id: string
    basis_hash: string
    recommendation: string
    lines: MatchLine[]
    issues: MatchIssue[]
    policy: { version: number; record: { mode: string; effective_from: string } }
  }
}
type Response = {
  current: Revision | null
  history: Revision[]
  needs_capture: boolean
  capabilities: { review: boolean; approve: boolean; admin: boolean }
  snapshot_status: Status | null
  match_status?: MatchStatus | null
}

function nextAction(code: string) {
  if (code === 'duplicate_confirmed') return 'Compare both source invoices and correct the duplicate record.'
  if (code === 'duplicate_candidate') return 'Compare invoice number, supplier, amount, date and PO before deciding.'
  if (code === 'price_variance') return 'Check the invoice price or approved PO price.'
  if (code === 'quantity_exceeds_available' || code === 'receipt_shortfall')
    return 'Check accepted receipts and earlier billings; reduce or defer the invoice quantity.'
  if (code === 'evidence_approval_required' || code === 'evidence_blocker')
    return 'Complete the source evidence review and prepare a current snapshot.'
  if (code === 'unallocated_line' || code === 'unknown_po_line')
    return 'Link this invoice line to the correct PO line.'
  if (code.includes('amount') || code.includes('total'))
    return 'Check the quantity, price, tax, discount and document total.'
  return 'Review the source record and reassess the match.'
}

function fieldLabel(path: string, lineIds: string[]) {
  if (!path.startsWith('lines.')) return path.replaceAll('_', ' ')
  const index = lineIds.findIndex((id) => path.startsWith(`lines.${id}.`))
  return `Line ${index + 1} � ${path.split('.').at(-1)?.replaceAll('_', ' ')}`
}

export function EvidencePanel({
  documentId,
  showPage,
}: {
  documentId: string
  showPage: (page: number) => void
}) {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ['ap-evidence', documentId],
    queryFn: () => api<Response>(`/ap/invoices/${documentId}`),
  })
  const [field, setField] = useState('')
  const [page, setPage] = useState('1')
  const [excerpt, setExcerpt] = useState('')
  const [reason, setReason] = useState('')
  const [company, setCompany] = useState('')
  const [system, setSystem] = useState('manual')
  const [po, setPo] = useState('')
  const [receipt, setReceipt] = useState('')
  const [allocations, setAllocations] = useState<Record<string, string>>({})
  const refresh = () => client.invalidateQueries({ queryKey: ['ap-evidence', documentId] })
  const capture = useMutation({
    mutationFn: () => api(`/ap/invoices/${documentId}/capture`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const attest = useMutation({
    mutationFn: () => {
      const current = query.data?.current
      if (!current || !field) throw new Error('Select a field')
      const value = current.fields[field]
      return api(`/ap/invoices/${documentId}/evidence`, {
        method: 'PUT',
        body: JSON.stringify({
          expected_revision: current.version,
          reason,
          fields: {
            [field]: {
              kind: 'corrected',
              raw: excerpt,
              normalized: value.effective,
              effective: value.effective,
              page: Number(page),
              excerpt,
              reason,
            },
          },
        }),
      })
    },
    onSuccess: refresh,
  })
  const prepare = useMutation({
    mutationFn: () =>
      api(`/ap/invoices/${documentId}/snapshots`, {
        method: 'POST',
        body: JSON.stringify({
          company,
          source_system: system,
          expected_revision: query.data?.current?.version,
          po_ids: po
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
          receipt_ids: receipt
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean),
          allocations,
        }),
      }),
    onSuccess: refresh,
  })
  const approve = useMutation({
    mutationFn: () =>
      api(`/ap/snapshots/${query.data?.snapshot_status?.snapshot.id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ payload_hash: query.data?.snapshot_status?.snapshot.payload_hash }),
      }),
    onSuccess: refresh,
  })
  const assessMatch = useMutation({
    mutationFn: () =>
      api(`/ap/snapshots/${query.data?.snapshot_status?.snapshot.id}/match`, { method: 'POST' }),
    onSuccess: refresh,
  })
  const approveMatch = useMutation({
    mutationFn: () =>
      api(`/ap/matches/${query.data?.match_status?.match.id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ basis_hash: query.data?.match_status?.match.basis_hash }),
      }),
    onSuccess: refresh,
  })
  if (query.isLoading)
    return (
      <Panel>
        <h2>Source evidence</h2>
        <p>Loading evidence…</p>
      </Panel>
    )
  if (query.error)
    return (
      <Panel>
        <h2>Source evidence</h2>
        <p role="alert">{query.error.message}</p>
      </Panel>
    )
  const data = query.data
  if (!data) return null
  const current = data.current
  const status = data.snapshot_status
  const match = data.match_status
  const error =
    capture.error || attest.error || prepare.error || approve.error || assessMatch.error || approveMatch.error
  return (
    <Panel>
      <h2>Source evidence and purchasing</h2>
      <p>Evidence approval, match approval, and ERP submit approval are separate decisions.</p>
      {data.needs_capture && <p>Current invoice values need a new evidence review.</p>}
      {data.capabilities.review && (
        <Button onClick={() => capture.mutate()} disabled={capture.isPending}>
          Capture current invoice
        </Button>
      )}
      {current && (
        <>
          <p>
            Revision {current.version} · {current.actor} · {new Date(current.at).toLocaleString()}
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Evidence</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(current.fields).map(([path, value]) => (
                  <tr key={path}>
                    <td>{fieldLabel(path, current.line_ids)}</td>
                    <td>{value.effective ?? 'Missing'}</td>
                    <td>{value.kind}</td>
                    <td>
                      {value.page ? (
                        <button type="button" onClick={() => showPage(value.page!)}>
                          Page {value.page}
                        </button>
                      ) : (
                        'Unknown'
                      )}
                      {value.excerpt && <blockquote>{value.excerpt}</blockquote>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.capabilities.review && (
            <details>
              <summary>Verify a field against the document</summary>
              <p>
                Save value corrections in Invoice fields first. Then record the page and exact
                excerpt you checked.
              </p>
              <label>
                Field{' '}
                <select value={field} onChange={(e) => setField(e.target.value)}>
                  <option value="">Select field</option>
                  {Object.keys(current.fields).map((p) => (
                    <option key={p} value={p}>
                      {fieldLabel(p, current.line_ids)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Page{' '}
                <input
                  type="number"
                  min="1"
                  value={page}
                  onChange={(e) => setPage(e.target.value)}
                />
              </label>
              <label>
                Source excerpt{' '}
                <textarea value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />
              </label>
              <label>
                Review reason <input value={reason} onChange={(e) => setReason(e.target.value)} />
              </label>
              <Button
                disabled={
                  attest.isPending ||
                  data.needs_capture ||
                  !field ||
                  !excerpt.trim() ||
                  reason.trim().length < 3
                }
                onClick={() => attest.mutate()}
              >
                Save verified evidence
              </Button>
            </details>
          )}
          <details>
            <summary>Revision history and corrections</summary>
            {data.history.map((r) => (
              <article key={r.version}>
                <h3>Revision {r.version}</h3>
                <p>
                  {r.actor} · {r.reason}
                </p>
                {Object.entries(r.changes).map(([p, c]) => (
                  <p key={p}>
                    {fieldLabel(p, r.line_ids)}: {c.before?.effective ?? 'Unknown'} →{' '}
                    {c.after.effective ?? 'Missing'} ({c.after.kind})
                  </p>
                ))}
              </article>
            ))}
          </details>
          {data.capabilities.review && (
            <details>
              <summary>Prepare purchasing evidence review</summary>
              <p>
                Use previously imported purchasing records and an administrator-verified supplier
                mapping and policy.
              </p>
              <label>
                Company <input value={company} onChange={(e) => setCompany(e.target.value)} />
              </label>
              <label>
                Source system <input value={system} onChange={(e) => setSystem(e.target.value)} />
              </label>
              <label>
                PO identifiers (comma separated){' '}
                <input value={po} onChange={(e) => setPo(e.target.value)} />
              </label>
              <label>
                Receipt identifiers (comma separated){' '}
                <input value={receipt} onChange={(e) => setReceipt(e.target.value)} />
              </label>
              {current.line_ids.map((id, i) => (
                <label key={id}>
                  Line {i + 1}: PO identifier and line identifier, separated by a colon{' '}
                  <input
                    value={allocations[id] || ''}
                    onChange={(e) => setAllocations({ ...allocations, [id]: e.target.value })}
                  />
                </label>
              ))}
              <Button
                disabled={prepare.isPending || data.needs_capture || !company}
                onClick={() => prepare.mutate()}
              >
                Prepare evidence snapshot
              </Button>
            </details>
          )}
        </>
      )}
      {status && (
        <section>
          <h3>Purchasing evidence: {status.status}</h3>
          {status.snapshot.blockers.length > 0 && (
            <ul>
              {status.snapshot.blockers.map((b) => (
                <li key={b}>{b.replaceAll('_', ' ')}</li>
              ))}
            </ul>
          )}
          {Object.entries(status.snapshot.inputs.sources).map(([kind, sources]) => (
            <div key={kind}>
              <h4>{kind === 'po' ? 'Purchase orders' : 'Goods receipts'}</h4>
              {sources.map((source) => (
                <article key={source.record.source_id}>
                  <strong>{source.record.source_id}</strong>
                  <p>
                    {source.record.status} · version {source.record.source_version} · synced{' '}
                    {new Date(source.synced_at).toLocaleString()}
                  </p>
                  <ul>
                    {source.record.lines.map((line) => (
                      <li key={line.source_line_id}>
                        {line.item_id}: {line.quantity} {line.uom}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          ))}
          {data.capabilities.approve && (
            <Button
              disabled={
                approve.isPending ||
                status.status !== 'awaiting_approval' ||
                status.snapshot.blockers.length > 0
              }
              onClick={() => approve.mutate()}
            >
              Approve this evidence snapshot
            </Button>
          )}
          <Button
            disabled={assessMatch.isPending}
            onClick={() => assessMatch.mutate()}
          >
            Assess three-way match
          </Button>
        </section>
      )}
      {match && (
        <section>
          <h3>Three-way match: {match.status.replaceAll('_', ' ')}</h3>
          <p>
            Policy revision {match.match.policy.version} · {match.match.policy.record.mode} mode ·
            effective {new Date(match.match.policy.record.effective_from).toLocaleDateString()}
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Invoice line / PO line</th>
                  <th>Price expected / actual / delta</th>
                  <th>Ordered / received</th>
                  <th>Billed / reserved / available</th>
                  <th>Invoice quantity</th>
                </tr>
              </thead>
              <tbody>
                {match.match.lines.map((line) => (
                  <tr key={line.line_id}>
                    <td>{fieldLabel(`lines.${line.line_id}.description`, current?.line_ids || [])} / {line.source_ref}</td>
                    <td>{line.expected_price} / {line.actual_price} / {line.price_delta} (limit {line.price_threshold})</td>
                    <td>{line.ordered} / {line.received}</td>
                    <td>{line.billed} / {line.reserved} / {line.available}</td>
                    <td>{line.invoice_quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {match.match.issues.map((issue, i) => (
            <article key={`${issue.code}-${issue.line_id || 'invoice'}-${i}`}>
              <strong>{issue.code.replaceAll('_', ' ')}</strong>
              {issue.line_id && <span> · {fieldLabel(`lines.${issue.line_id}.description`, current?.line_ids || [])}</span>}
              <p>{Object.entries(issue.facts).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p>
              <p>Next: {nextAction(issue.code)}</p>
            </article>
          ))}
          <ApExceptionDecisions documentId={documentId} canReview={data.capabilities.review}
            isAdmin={data.capabilities.admin} matchId={match.match.id} />
          {data.capabilities.approve && (
            <Button
              disabled={approveMatch.isPending || match.status !== 'ready_for_approval'}
              onClick={() => approveMatch.mutate()}
            >
              Approve match and reserve quantity
            </Button>
          )}
          {match.status === 'stale' && <p>Source or policy changed. Run a new match assessment.</p>}
          <PostingPanel matchId={match.match.id} basisHash={match.match.basis_hash}
            canApprove={data.capabilities.approve} isAdmin={data.capabilities.admin}
            lineIds={current?.line_ids ?? []} />
        </section>
      )}
      {error && <p role="alert">{error.message}</p>}
    </Panel>
  )
}
