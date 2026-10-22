# AI Document — Invoice Review: Project Tour

Invoice Review connects AI extraction, source-linked review, invoice–purchase-order–receipt
matching, exception resolution and separately approved ERPNext posting. Submitted invoices and
general-ledger entries are independently checked before the application records verified posting.

## One-minute review path

1. See the [review workspace](assets/screenshots/review.png) or watch the
   [captioned demo](assets/demo/invoice-review-demo.mp4).
2. Read the [engineering case study](PORTFOLIO_CASE_STUDY.md) for product decisions and architecture.
3. Inspect the [v2 technical evaluation](evidence/invoice-review-v2/PHASE-6.md) for frozen quality,
   discrepancy, posting and revision-replay results.
4. Check the [paired draft timing result](erpnext-paired-draft-timing-results.md) for the separate
   six-invoice workflow comparison.
5. Review the [packaged release evidence](evidence/invoice-review-v2/PHASE-7.md) for browser review,
   response-loss recovery, restart and storage restoration.

## Evidence summary

| Claim                     | Result                                                                 | Scope                                                                                                                                               | Exact evidence                                                             |
| ------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Whole-invoice correctness | **50/50**                                                              | Original extracted values and required page/excerpt provenance on frozen synthetic invoices; 40 quality families including ten duplicate pairs      | [Quality report](evidence/invoice-review-v2/quality-holdout/report.json)   |
| Discrepancy detection     | **Quantity 30/30; price 10/10; receipt 20/20; duplicate 10/10**        | Controlled labeled scenarios; zero false holds among 20 eligible invoices                                                                           | [Discrepancy report](evidence/invoice-review-v2/discrepancies/report.json) |
| Verified ERP outcomes     | **20/20 eligible submissions; 30/30 exception dispositions**           | Local ERPNext invoice/ledger read-back and authorized final dispositions for non-payable cases                                                      | [Technical evaluation](evidence/invoice-review-v2/PHASE-6.md)              |
| Restart replay            | **20/20; zero duplicate ERP effects**                                  | Replays returned the same ERP target                                                                                                                | [Posting report](evidence/invoice-review-v2/posting/report.json)           |
| Revision recovery         | **Three dated revisions**                                              | Supplier alias mapping, price tolerance and receipt correction; verified posting and 70/70 development regression cases correct after each revision | [Replay report](evidence/invoice-review-v2/replay/report.json)             |
| Paired draft timing       | **153s to 49s median (68.0% lower)**                                   | Separate six-invoice synthetic study; one operator; local sandbox; endpoint is a verified ERPNext draft                                             | [Timing result](erpnext-paired-draft-timing-results.md)                    |
| Packaged recovery         | **Verified lost-response recovery, restart and SQLite/upload restore** | Controlled local release checks, including reconciliation while new ERP writes are disabled                                                         | [Release evidence](evidence/invoice-review-v2/PHASE-7.md)                  |

The timing benchmark measures median elapsed time to a verified Purchase Invoice Draft. Active
work and system waiting were not separated. It does not measure submitted-posting time savings
and is not part of the 50-invoice quality cohort. The existing timing result remains the time-saving
evidence; a new full-posting operator study remains optional.

## The problem

Reading an invoice does not establish whether it is payable. Reviewers must verify the supplier,
compare quantities and prices with purchasing evidence, check receipts and prior billing, and
resolve duplicates before creating another accounting entry.

The workspace keeps source evidence, corrections, matching decisions, approvals and ERP outcomes
connected. AI proposes values; application controls establish eligibility; people authorize ERP
actions. Payment execution is outside the product scope.

## What the project shows

| Capability                             | How it works                                                                                               | Evidence                                                         |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Source-linked review                   | Original extraction and provenance remain available after correction; reviewers attest evidence.           | [Case study](PORTFOLIO_CASE_STUDY.md)                            |
| Deterministic three-way matching       | Quantity, price, receipt, prior billing, reservations and duplicate checks determine eligibility.          | [Technical evaluation](evidence/invoice-review-v2/PHASE-6.md)    |
| Version-bound authority                | Changed evidence or matching rules invalidate stale approvals; exceptions require authorized dispositions. | [Revision replay](evidence/invoice-review-v2/replay/report.json) |
| Controlled posting                     | Draft creation and submission require separate approvals; invoice and ledger read-back verify the outcome. | [Posting report](evidence/invoice-review-v2/posting/report.json) |
| Recovery from uncertain writes         | A lost response leaves an unknown outcome until read-only reconciliation checks the known operation.       | [Release evidence](evidence/invoice-review-v2/PHASE-7.md)        |
| Persisted review and operation history | Corrections, actors, reasons, approvals and ERP operation events remain inspectable.                       | [Architecture](ARCHITECTURE.md)                                  |

## Representative cases

| Case                                       | Expected behavior                                                                                                                      |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Clean, eligible invoice                    | Require evidence/match approval, create and verify the draft, then require separate submit approval and verify invoice/ledger results. |
| Missing or unsupported source value        | Keep the value unverified until source-linked correction or attestation establishes the evidence.                                      |
| Quantity, price or receipt discrepancy     | Hold the invoice for authorized resolution; changed purchasing evidence requires reassessment.                                         |
| Duplicate invoice                          | Hold the duplicate and preserve its relationship to the prior invoice.                                                                 |
| Supplier mapping or purchasing-rule change | Recompute the affected assessment and invalidate stale approval where its basis changed.                                               |
| Lost submit response                       | Retain the known operation and reconcile the existing ERP target before another write is considered.                                   |
| New ERP writes disabled                    | Continue authorized read-only reconciliation of an earlier operation.                                                                  |

## Current limitations

- The v2 quality cohort contains developer/AI-assisted synthetic, one-line USD invoices with explicit
  zero tax. Results establish these controlled scenarios, not accuracy on arbitrary customer invoices.
- The timing evidence covers one operator and six synthetic draft cases. Full-posting handling time
  and production business impact have not been measured.
- The three revision checks cover supplier mapping and purchasing rules; they do not establish
  resilience to arbitrary supplier-layout changes.
- Posting and recovery were validated in a local ERPNext sandbox. Customer-production concurrency,
  accounting sign-off, production tenancy and off-host disaster recovery require separate validation.
- The [earlier Azure validation](azure-live-validation.md) covered mock-provider intake, followed by
  teardown. It did not validate the current ERP posting workflow in the cloud;
  [Phase 8](evidence/invoice-review-v2/PHASE-8.md) retains the local/sandbox evidence boundary.

See the [documentation index](INDEX.md) and [runbook](RUNBOOK.md) for implementation details and
reproduction prerequisites.
