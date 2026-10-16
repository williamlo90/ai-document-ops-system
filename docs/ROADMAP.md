# Roadmap

The implemented product covers source-linked invoice extraction/review, versioned PO/receipt
matching, duplicate intelligence, authorized exception handling and separately approved, verified
ERPNext sandbox posting. [Current evidence](INDEX.md) records evaluation and packaged release scope.

## Completed Release Scope

- Human review preserves original extraction and records corrections and source evidence.
- Matching accounts for received, billed and reserved quantities and checks price policy.
- Exceptions retain ownership, reason, evidence and authority; stale assessments cannot authorize posting.
- Draft and submit operations have separate approvals, durable identity and invoice/ledger read-back.
- Packaged local runtime supports restart, unknown-outcome reconciliation and SQLite/upload restore;
  PostgreSQL persistence and migration checks are available.
- [Phase 8](evidence/invoice-review-v2/PHASE-8.md) explicitly skips a new optional cloud run.

## Next Handoff

Phase 9 audits the public claim-to-evidence mapping and prepares the CV handoff in its separate task.
The six-invoice verified-draft timing result keeps its original scope; a new human study of the
full submitted-posting workflow remains optional.

## Future Validation

Broader supplier layouts, multiline/tax/currency cases, independent operator studies, concurrency,
customer-data governance and cloud recovery need their own scoped evidence before related claims.
A hosted release would require a separately reviewed deployment, resource budget and teardown plan.

Payment execution, an unrestricted chatbot, production multi-tenancy and a second document type
are outside the current product scope.
