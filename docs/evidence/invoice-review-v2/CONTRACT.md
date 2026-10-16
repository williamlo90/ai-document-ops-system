# Invoice Review V2 — outcome and measurement contract

Contract version: **2.1.0**, effective **2026-10-16**. Baseline: `83ffd12`.
Measurement definitions and targets remain **2.0.0**, frozen on **2026-10-13**.
Measured reports retain their original contract version, freeze and source hashes.
Changes to metrics, thresholds or evaluation datasets require a new measurement
version and freeze before inspecting final outputs.

## Phase 6 completion

Phase 6 completes when the frozen technical evaluation passes all extraction,
validation, discrepancy, duplicate, safe-posting, completion, regression and
restart gates, with independent ERP invoice/ledger evidence and runtime samples.
The acceptance record is [phase6-validation.json](phase6-validation.json); the
original measurement check is [technical-validation.json](technical-validation.json).

The manual-versus-assisted operator study is **optional and deferred**. Its absence
does not block the Phase 6 checkpoint or Phase 7 release validation. Prepared study
inputs and tooling remain available for a later study. No human time saving,
productivity improvement or manual-versus-assisted advantage is claimed without
that study. Technical results describe their controlled synthetic sandbox scope;
production readiness remains subject to separate release validation.

## Scope

Extend the existing FastAPI/React modular monolith. Reuse document processing,
review, correction events, audit, repositories and integration recovery.
Add procurement and deterministic matching modules; keep AI proposals separate
from approval authority. Preserve SQLite for local work and PostgreSQL compatibility.

V1 supports PO-backed goods invoices, partial receipts, multiple invoices per PO,
limited multiple POs per invoice with the same company/vendor/currency, cumulative
billed/reserved quantities, duplicate detection, price/quantity/receipt exceptions,
source-linked review, and ERPNext sandbox draft then separately approved submit.
PO/receipt input starts with validated JSON/CSV; ERP synchronization is read-only.

Non-PO, services, prepayments, returns and credit notes outside this scope require
explicit hold/review. No auto-approval, payment execution, supplier messaging,
three-document OCR pipeline, or production deployment is included.

## Outcomes

- `posted_verified`: an eligible, separately submit-approved revision has exactly
  one confirmed ERP target; read-back matches company, supplier, bill identity,
  currency, dates, line count/items/UOM/quantity/rates, tax, accounts, totals,
  PO/receipt links and independently expected accounting entries. `docstatus=1`
  is necessary but insufficient. Unknown/mismatch never counts as success.
- `exception_resolved`: all blocking issues have an authorized disposition tied
  to current evidence and revision, matching the oracle. A corrected payable
  invoice continues to posting; an intentionally non-payable case ends with a
  documented rejection/confirmed duplicate or other final authorized disposition.
  Waiting for information/receipt, a note, or an unresolved hold is not completion.
- `correct_hold`: the assessment correctly prevents an unsafe action. This can
  pass decision scoring while still failing end-to-end resolved completion.
- `assessment_incomplete`: provider failure, missing observation or unavailable
  required source prevents assessment. Never reinterpret it as clean validation.
- `unknown`: a remote effect might have happened. Retain reservation, reconcile
  the existing operation/target, and prohibit blind retry or a fresh invoice.

## Required extraction and provenance

The oracle declares required header paths and line paths before a run. All eight
existing header fields remain labeled, including explicit null for absent values.
Goods lines require description, UOM, quantity, unit_price and amount; tax/discount
and references are required when present/applicable according to the oracle.
Missing keys differ from explicit null. Unsupported values cannot earn exact match.

Compare original extraction before reviewer edits. Report corrected final values
separately using the same oracle. Preserve observed, normalized, derived and
reviewer-corrected values. Each required non-null value needs appropriate evidence:
page/excerpt for observed, transformation plus source for normalized, formula and
input references for derived, actor/time/reason/source for corrected. A computed
amount does not become a printed amount. No bounding boxes are invented.

Normalize whitespace/case for description/vendor/currency, unambiguous ISO dates
and Decimal representations. Invoice numbers retain meaningful characters.
Amounts use declared currency precision and ROUND_HALF_UP; quantity/unit prices
retain declared source precision. Start currency profiles IDR/USD with two-decimal
amount precision, versioned explicitly. No business tolerance in extraction scoring.
No locale guessing on ambiguous strings. Matching business tolerances are separate.

Line alignment is deterministic and one-to-one: explicit stable reference when
available; otherwise normalized description + UOM identity. Treat repeated identical
rows as a multiset. Remaining non-identical rows with ambiguous identity fail
whole-invoice exact and report ambiguity; do not select a permutation that maximizes
numeric correctness. Any diagnostic tie-break must be versioned and reported.

## Metric definitions and release targets

Every report includes numerator, denominator, N, contract/evaluator version, input
stage, dataset/model/prompt/config hashes, source commit and execution timestamp.
Zero denominator is null/N/A, never 0% or 100% success. A gate with no eligible
samples is unmeasured, not passed. Failures/unknowns remain in scheduled denominators.

| Metric                             | Numerator / denominator                                                                                                                                              | Frozen target                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `whole_invoice_exact`              | Original extractions with all required header/line values, provenance, line count correct and no missing/extra/ambiguous rows / all scheduled fully labeled invoices | >=90%                                                             |
| Header field exact                 | Correct expected header values / all required labeled header values                                                                                                  | Diagnostic, no substitute for whole invoice                       |
| Line field exact                   | Correct expected line values / all required labeled line values; unmatched expected values fail                                                                      | Diagnostic; extra rows also affect line precision and whole exact |
| Exact-line precision / recall      | Fully correct one-to-one rows / predicted rows and / expected rows                                                                                                   | Report both                                                       |
| Processing / validation completion | Successfully executed stage / all scheduled invoices                                                                                                                 | >=95% each                                                        |
| Validation exact                   | Completed check with exact expected issue set / all validation-labeled invoices                                                                                      | >=95%; error != empty issue set                                   |
| Discrepancy recall                 | TP / (TP+FN), separately quantity, price, duplicate, receipt                                                                                                         | >=95% each                                                        |
| Duplicate precision                | TP / (TP+FP) on labeled candidate pairs                                                                                                                              | >=95%, with transaction counts too                                |
| Transaction false-hold rate        | Oracle-clean transactions unnecessarily held or sent to mandatory exception review / all oracle-clean transactions                                                   | <=5%                                                              |
| Unsafe-ready rate                  | Unsafe transactions recommended ready / all oracle-unsafe transactions                                                                                               | 0 in critical suite and final evaluation                          |
| Posting correctness                | Submitted records whose full independently specified record and ledger match / all submitted records for which read-back completed (including mismatches)            | 100% in controlled suite                                          |
| Posting completion                 | Correct verified submissions / all scheduled oracle-eligible submissions                                                                                             | >=95%; eligibility fixed before run                               |
| Duplicate remote effects           | Additional ERP invoices/effects for the same authorized operation                                                                                                    | 0                                                                 |
| Correction recovery                | Originally wrong invoices made fully correct / originally wrong invoices receiving documented correction                                                             | Report; no invented target                                        |
| Regression retention               | Previously correct development cases still correct after revision / previously correct replay cases                                                                  | 100% critical suite; report all cases separately                  |
| Time reduction                     | `1 - median(assisted paired times)/median(manual paired times)` for same-outcome correct completed pairs                                                             | >0 to claim a reduction; no fixed marketing percentage            |

For discrepancy scoring, positive transactions with incomplete assessment count as
FN unless the actual detector emitted the correct issue. On clean transactions,
incomplete assessment is reported separately and also counted as a false hold if
it prevents progression. Mandatory routine human approval alone is not a false hold.
Record TP/FP/FN/TN per category and multi-label intersections; count each transaction
once in transaction-level metrics. Never score a replacement evaluator heuristic.

Posting correctness does not exclude read-back mismatches from its denominator.
Unknown/unreadable submissions are reported as unverifiable and fail completion;
also publish all attempted/submitted/unverified counts to expose selection effects.

If the optional operator study is performed, its cohort is separate from quality holdout. Report original and final
whole-invoice correctness on that same cohort; a combined CV time/quality bullet
uses final same-cohort correctness and explicitly says it is after review. Keep
original extraction correctness visible separately. Report all scheduled pairs,
failed/skipped pairs, active handling and elapsed time, counterbalanced order, and
single-operator status. Do not compare draft versus posted or omit failed cases.

Measure p50/p90/p95 per API, queue, worker, OCR, extraction, match and ERP stage
with sample sizes, failed requests, cost and usage. These are local measurements,
not production SLOs. No latency pass target is invented before workload freeze.

## Supporting contracts

- [Baseline and archive reconciliation](BASELINE.md)
- [Dataset protocol and manifest](DATASET.md)
- [Permission, state and API delta](DESIGN.md)
- [Claim-to-evidence matrix](CLAIMS.md)
- [ERP capability check and resource profile](ERP-PREFLIGHT.md)
- [Phase ledger and learning checkpoint](PHASE-STATUS.md)

Thresholds are engineering gates on controlled samples, not production guarantees.
If they fail, preserve the result and change implementation on development data.
Do not tune on final holdout or revise thresholds after seeing its scores.
