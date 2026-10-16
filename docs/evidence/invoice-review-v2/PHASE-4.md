# Phase 4 — duplicate checks and exception resolution

Phase 4 turns three-way match issues into versioned work items. It adds a
deterministic duplicate check to each assessment and keeps AP approval tied to
the current evidence and policy. ERP posting remains disabled.

## Decision rules

- Invoice number comparison removes punctuation and case. OCR-confusable
  characters (`O/0`, `I/L/1`, `S/5`, `B/8`) produce a **candidate**, never an
  automatic confirmed duplicate. Supplier identity uses the current verified
  company mapping, not a free-text vendor name alone. The detector compares
  reviewer-verified supplier, number, date and total on current invoices in
  the same workspace and company. Exact number, amount and a date within 30
  days plus a date within one day or overlapping PO produce a confirmed duplicate;
  weaker exact-number evidence or an OCR-like number with supporting amount
  and date/PO evidence produces a candidate. A recurring invoice on a
  different PO 20 days later remains a negative control, as do different
  numbers, suppliers or dates outside the window. The comparison corpus is part of the
  match basis, so a later invoice correction invalidates an older approval.
- Each issue creates an append-only case with code, source facts, owner,
  reason, evidence references, actor, authorizer, match ID and basis hash.
  Cases are `open`, `needs_info`, `resolved`, `waived` or `superseded`.
  Reassessment reopens a recurring issue when its basis changes and
  supersedes an issue that disappears. A reviewer can mark `resolved` only
  after the issue has disappeared from a current reassessment; adding a note
  or selecting `needs_info` never removes a blocker.
- An administrator may configure a versioned waiver policy for only
  `price_variance` (within a maximum per-unit delta) or
  `duplicate_candidate`. Waivers require an evidence reference and admin
  authorization. Confirmed duplicates, missing evidence, receipt/quantity
  blockers and unknown ERP outcomes cannot be generically waived. A changed
  policy or match basis makes the earlier decision stale. AP approval
  re-evaluates under the transaction lock before reserving quantity.

## Operator workflow

1. Complete reviewed evidence and run `POST /ap/snapshots/{id}/match`.
2. Inspect the purchasing match exceptions in Inbox, sorted by unresolved
   priority and age. Open the invoice to inspect the issue facts and source.
3. Correct invoice fields, PO allocation, supplier mapping or imported
   purchasing evidence as needed; prepare a new snapshot, approve its
   evidence and reassess. A stale match cannot be approved.
4. `GET /ap/exceptions?document_id={id}` returns case history. `PUT
/ap/exceptions/{id}` records an owner, reason, evidence reference and
   optimistic `expected_version`/`expected_match_id`. Reviewers can request
   information or record a resolution after reassessment. Admins may use
   `PUT /ap/exception-policy` and authorize only allowed waivers.
5. `GET /ap/matches/{id}` shows readiness. Only a current ready match, or a
   match whose every active issue has a valid waiver, can be approved.

## Validation and limits

The labeled fixture executes the actual match detector: quantity, price,
receipt and duplicate categories each have one positive and one negative;
all four category matrices are TP 1, FN 0, FP 0, TN 1. No clean fixture was
held (0/4). Separate tests cover punctuation, OCR candidates, supplier alias
boundaries, recurring invoices, unauthorized waivers, source correction,
reopening/staleness and blocked approval. This is a small synthetic regression
set, not a population estimate. The Phase 4 tests passed on SQLite and an
isolated PostgreSQL database. No live ERP write or OCR call is claimed. See
[phase4-validation.json](phase4-validation.json) for run counts.
