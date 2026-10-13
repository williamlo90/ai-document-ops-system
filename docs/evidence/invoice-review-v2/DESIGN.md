# Permission, state and API contract delta

Design version 2.0.0. Proposed contracts below are not implemented endpoints.

## Data and authority

Every entity is workspace/company scoped. Keep canonical supplier separate from
OCR display name; aliases require verification. Use Decimal strings over JSON.
New entity groups: invoice revisions/lines/field provenance; PO/PO lines;
receipt/receipt lines; supplier/item/UOM mappings; policy versions; allocations;
immutable match runs; exception resolutions; approval snapshots; ERP operations.
All source records retain source ID, version, status and synchronization timestamp.

PO/receipt records are authoritative structured inputs; model output may suggest
links but cannot establish received quantity. Available receipt quantity equals
net accepted receipts minus committed billings and active reservations of other
invoices. Deduplicate local/ERP representations of the same delivery. Approval and
reservation commit atomically; lock all affected PO lines in stable order and
revalidate cumulative limits. SQLite and PostgreSQL must implement equivalent
invariants. Release reservations only after safe cancellation/reconciliation.

Default strict policy has zero price/quantity business tolerance. A versioned demo
policy may specify `abs(delta) <= max(abs_limit, abs(expected)*relative_limit)`.
Invoice date selects effective purchasing policy; a later policy revision requiring
reassessment invalidates affected approvals explicitly, rather than silently
rewriting an old match. Reject unsupported currency/UOM conversion.

Source freshness: before approval/submit require current source versions; online
ERP snapshots older than 5 minutes require refresh. Imported fixture snapshots
are authoritative only inside the explicit local fixture profile. Before submit,
read current ERP draft/source versions and rely on ERP's transaction constraints
too; local checks alone cannot prevent an external concurrent change.

## Permission matrix

| Action                                              | Uploader | Reviewer | AP approver | Admin                            |
| --------------------------------------------------- | -------- | -------- | ----------- | -------------------------------- |
| Upload and inspect own permitted workspace          | Yes      | Yes      | Yes         | Yes                              |
| Correct/link evidence, propose exception resolution | No       | Yes      | Yes         | Only with reviewer capability    |
| Approve invoice/reserve quantity                    | No       | No       | Yes         | Only with AP approver capability |
| Approve submit as a separate recorded action        | No       | No       | Yes         | Only with AP approver capability |
| Change policy/mapping/import or sync procurement    | No       | No       | No          | Yes                              |
| Reconcile unknown operation                         | No       | No       | Read only   | Yes; no blind retry              |

Capabilities are server-owned and mapped explicitly to existing role sessions.
Admin is not an automatic AP approval bypass. A single demo operator may hold both
capabilities; record separate approval actions without claiming two-person control.
Every decision records actor, time, reason, scope and relevant versions.

## State contracts

Retain DocumentStatus. `exported` remains historical export, never means posted.
Assessment: incomplete → ready/hold/needs_review. Changed input supersedes an
immutable match and invalidates approval; it never edits historical match evidence.
Exceptions: open → needs_info/resolved/waived/superseded. A waiver requires authorized
policy and evidence; confirmed duplicates, missing evidence and unknown ERP effects
cannot be waived generically. New input can reopen an issue on the new revision.

Approval snapshot binds invoice revision, match ID, PO/receipt/allocation versions,
policy and mapping versions, frozen payload hash and action scope. The second
submit approval additionally binds ERP draft ID/version/hash. All commands reject
stale snapshots. Keep separate durable create_draft and submit_draft operations:
pending → confirmed/failed/unknown; unknown → confirmed or safe failed only after
reconciliation. Read-back mismatch is reconciliation_required, not posted_verified.

## Proposed application API

| Route                                      | Contract                                                                                                        |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `POST /procurement/imports`                | Admin; validated batch, source IDs/versions and idempotency key; atomic rejection of malformed/conflicting rows |
| `POST /procurement/sync`                   | Admin; fetch-only ERP adapter; creates local versioned snapshots                                                |
| `GET /invoices/{id}/match`                 | Scoped latest assessment + input versions + evidence refs                                                       |
| `POST /invoices/{id}/match`                | Reviewer; expected invoice revision, recompute immutable result                                                 |
| `POST /exceptions/{id}/resolve`            | Reviewer/authorized approver per type; expected match version, evidence and resolution code                     |
| `POST /invoices/{id}/approvals`            | AP approver; expected revision/match/source versions; atomic allocation reservation                             |
| `POST /invoices/{id}/erp/draft`            | Approved snapshot and durable operation key; verify target draft                                                |
| `POST /invoices/{id}/erp/submit-approvals` | AP approver; binds verified ERP draft and all current versions                                                  |
| `POST /invoices/{id}/erp/submit`           | Valid submit approval and same target ERP ID; sandbox flag required                                             |
| `POST /invoices/{id}/erp/reconcile`        | Admin; inspect existing operation before any further write                                                      |

Missing permission → 403; outside workspace → 404; stale revision/idempotency
payload conflict → 409; invalid input → 422. Replayed identical operation returns
its existing result; different payload under same key is rejected. Async work
returns operation ID and an explicit pending/unknown state. Audit mutations in the
same transaction as their local effects. Never hold a database lock during remote I/O.

Existing review/export endpoints retain V1 compatibility, but cannot bypass V2
approval gates for V2-enabled invoices. Add migrations in both stores; legacy
provenance is unknown and needs reassessment. Rollback disables new commands while
preserving operation/allocation ledgers and reconciliation access.

UI extends existing Review (fields/match/exceptions/activity), Inbox and Exports.
Evidence links open exact source snapshots. Backend capability/state responses own
enabled actions; frontend labels cannot grant approval or posting authority.
