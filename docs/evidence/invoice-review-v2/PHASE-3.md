# Phase 3 — deterministic three-way match and cumulative allocation

Phase 3 compares the reviewed invoice with versioned purchase orders, accepted
receipts, prior committed billings, and reservations from approved matches. It
does not post to ERPNext. Phase 2 evidence approval remains a prerequisite.

For a PO of 100 units at 50, a receipt of 70 units, and an invoice for 100 units
at 55, the result lists **price variance 5 per unit** and **quantity shortfall
30** independently. For received 70, previously billed 50, and a new invoice
of 30, available quantity is 20 and approval is blocked.

## Decision contract

- An administrator configures a versioned `MatchPolicy` with an effective date,
  price tolerance (absolute or relative), quantity review tolerance, amount
  tolerance, rounding precision, mode, and approver authority. The invoice date
  selects the latest applicable revision. Revisions may retain the same
  effective date but may not move backward. Policy changes make older match
  assessments stale.
- Explicit reviewed allocations choose the PO line. The assessor suggests
  candidate PO lines using verified item/UOM mappings when an allocation is
  absent, but no suggestion is auto-approved. AI may propose candidate mappings
  upstream; the matching decision does not depend on model output.
- A receipt contributes quantity only when submitted and its PO line, item and
  UOM agree. Cancelled or stale source revisions invalidate the evidence
  snapshot. The conservative quantity ceiling is always the smaller of ordered
  and accepted received quantity, including in ordered comparison mode.
- Available quantity per PO line is `min(ordered, accepted_received) -
committed_billings - active_reservations`. Several invoice lines aimed at
  the same PO line are summed before the ceiling check. A configured quantity
  tolerance can classify a small overage as `needs_review`; it never permits
  reserving more than the available quantity.
- The immutable match record binds the evidence snapshot, evidence approval,
  purchasing versions, billing versions, policy revision and reservation state.
  Each issue retains its code, line/source reference and numeric facts. The
  output is `ready_for_approval`, `hold`, `needs_review`, or
  `assessment_incomplete`.
- An AP approver or administrator may approve only a current ready result.
  Approval and one reservation per allocated PO line commit under the shared
  workspace transaction lock. A second request re-evaluates inside the lock;
  simultaneous approvals cannot reuse quantity. An existing active reservation
  also prevents a second approval for the same invoice.
- Reservations survive timeouts and later source changes. They are released
  only through an administrator's explicit reconciliation record with a reason
  and external reference. No automatic timeout release occurs. An old approval
  is immutable and is never silently converted into a new approval.

## API and operator sequence

1. Complete Phase 2 evidence capture, attestation, purchasing import/sync,
   snapshot and evidence approval.
2. `PUT /ap/match-policy` as admin, with `company`, timezone-aware
   `effective_from`, `mode`, tolerances as decimal strings, `rounding_places`,
   `approver_role` and `reason`.
3. If prior billed quantities exist, `POST /ap/billings/import` as admin with
   `records`. Each `billing_id` uniquely identifies one billing line within its
   company and source system. Include source version/time, PO/PO-line, UOM,
   quantity and `committed` or `cancelled` status. Advance the version to
   revise/cancel a billing. Quantity must already be in the referenced PO UOM.
4. `POST /ap/snapshots/{id}/match` to save an immutable assessment, then
   `GET /ap/matches/{id}` to recheck current status. The Review Workspace shows
   per-line figures and all exceptions with next actions.
5. `POST /ap/matches/{id}/approve` with the `basis_hash` from the assessment
   to approve and reserve quantity. The server rejects stale/held assessments.
6. After independently confirming a cancellation or reconciliation, an admin
   may call `POST /ap/matches/{id}/release` with `reason` and
   `reconciliation_ref`. This is a manual attestation, not an ERP transaction.

Missing PO/receipt references are retained as blockers and can be assessed as
`assessment_incomplete`. Supplier, currency, source status, evidence, item/UOM
and version checks from Phase 2 remain mandatory. Invoice price, quantity,
amount, tax and discount checks are additive. Match approval does not set
`posting_ready`; later phases own exception resolution and ERP delivery.

## Validation

The focused suite covers exact and partial match, price and quantity boundaries,
prior billing, repeated item lines, missing sources, policy revision, cancelled
receipt, cross-workspace and role isolation, stale API approval, sequential and
concurrent allocation, and explicit release. The same matching suite runs on
SQLite and an isolated PostgreSQL database. Frontend tests check exception
presentation and the disabled approval button for held results. See
[phase3-validation.json](phase3-validation.json) for the execution record.
