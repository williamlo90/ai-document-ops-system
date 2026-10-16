# Invoice Review — Engineering Case Study

## Problem and Outcome

An accounts-payable operator must establish more than what an invoice says. The supplier must
map to the accounting system, purchased quantities must agree with received and already billed
quantities, prices must satisfy policy, and duplicates must be held before another accounting
entry is created.

Invoice Review connects invoice extraction, source-linked correction, three-way matching,
authorized exception resolution and separately approved ERPNext submission. The outcome is
verified against the submitted Purchase Invoice and its general-ledger entries.

## Product Decisions

The workspace keeps the PDF beside proposed values. Original extraction values and provenance
remain available after corrections. Source snapshots and matching results are versioned, so a
changed supplier mapping, purchase order, receipt or rule can invalidate stale approval.

AI proposes values; deterministic application controls establish eligibility; people authorize
consequential actions. Draft creation and submission use separate approvals. Payment execution
is outside the product scope.

[![Invoice review workspace](assets/screenshots/review.png)](assets/demo/invoice-review-demo.mp4)

## Architecture and Authority

FastAPI provides document intake, review, matching and posting APIs. A background worker runs OCR
and structured extraction. React/TypeScript provides the operator workspace. SQLite/private local
storage is the default; PostgreSQL persistence and migrations have also been exercised.

The tested real-provider path combines OCR.space Engine 3 with structured OpenAI extraction.
API-key failover handles eligible provider failures. It does not turn a failed extraction into an
approved record. Credential-free mock providers support setup and deterministic regression checks.

ERP actions use durable operation identities and append-only history. An unavailable response
cannot establish that a write failed: the operation stays unknown until read-only reconciliation
checks the target. Disabling new ERP writes preserves the ability to reconcile an earlier effect.

See [architecture](ARCHITECTURE.md), [matching/posting evidence](evidence/invoice-review-v2/PHASE-6.md)
and [the integration boundary](erpnext-integration-design.md).

## Evaluation

| Result                                         | Scope                                                                                               | Evidence                                                                 |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 50/50 whole invoices correct                   | Frozen synthetic values and required source provenance; 40 quality families and ten duplicate pairs | [Quality report](evidence/invoice-review-v2/quality-holdout/report.json) |
| 20/20 eligible submissions verified            | Local ERPNext invoice and ledger read-back                                                          | [Posting report](evidence/invoice-review-v2/posting/report.json)         |
| 30/30 non-payable cases resolved               | Authorized exception dispositions                                                                   | [Evaluation](evidence/invoice-review-v2/PHASE-6.md)                      |
| No false holds or unsafe/duplicate ERP effects | Controlled labeled discrepancy cohort                                                               | [Discrepancies](evidence/invoice-review-v2/discrepancies/report.json)    |
| 20/20 restart replays                          | Same ERP target after replay                                                                        | [Posting report](evidence/invoice-review-v2/posting/report.json)         |
| Three dated rule/mapping revisions             | Verified recovery with retention of previously correct development cases                            | [Replay](evidence/invoice-review-v2/replay/report.json)                  |

The quality cohort is developer/AI-assisted synthetic data: one-line USD invoices with explicit
zero tax. These observations demonstrate the controlled cases, not general customer accuracy.

A separate single-operator benchmark measured **68.0% lower median elapsed workflow time**:
49 seconds assisted versus 153 seconds manual across six synthetic invoices. Both conditions ended
at a verified ERPNext **draft**. This is not submitted-posting time savings and does not combine
with the 50-invoice cohort. See [the paired timing method and results](erpnext-paired-draft-timing-results.md).

## Release and Failure Recovery

The [packaged release validation](evidence/invoice-review-v2/PHASE-7.md) exercised the Docker
API/worker, a real-provider canary, browser review, role boundaries, migrations, restart, storage
restore and independent ERP invoice/ledger checks. A controlled transport fault discarded the
successful submit response; reconciliation recovered the existing target without another posting.
The backup drill restored SQLite and upload objects into a separate directory and checked integrity
and hashes without overwriting the source.

The seeded demo has bounded resources, loopback ports, non-root containers and ERP writes disabled.
Run it with `scripts/start_release.ps1 -Seed` after [setup](docker_profile.md).

## Deployment Boundary

The earlier [temporary Azure validation](azure-live-validation.md) exercised mock-provider intake
through `needs_review`, and its record includes teardown. It did not validate the current full
ERP posting workflow in Azure. [Phase 8](evidence/invoice-review-v2/PHASE-8.md) explicitly skips a
new cloud deployment because the selected outcome is already supported by local/sandbox evidence.

## Reproduce and Inspect

Use [the runbook](RUNBOOK.md) for credentials, provider setup and ERP prerequisites, and
[the evidence index](INDEX.md) for measurement contracts and dated results. Customer-production
accuracy, sustained production concurrency and cloud disaster recovery remain outside the tested
scope. A new human study of the full posting workflow remains optional.
