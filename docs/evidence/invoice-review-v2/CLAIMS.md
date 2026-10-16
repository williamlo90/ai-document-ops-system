# Claim-to-evidence contract

Each claim requires the evidence listed below. Reserved paths may remain absent
until their producing work is performed. CV updates remain a Phase 9 task.

| Claim                                                                    | Required proof / reserved path relative to this directory                                                                                                                                    | Phase   |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| OCR → PO/receipt match → source-linked exceptions → approved ERP posting | `journey/report.json`: invoice/source hashes, immutable matches, approvals, submitted read-back and negative cases; `journey/screens/`                                                       | 2–5     |
| Whole-invoice correctness on held-out invoices                           | `quality-holdout/report.json`: frozen oracle/evaluator, original extraction values/provenance, all scheduled invoice denominator, failed/unknown cases                                       | 1, 6    |
| Reduced invoice-to-ERP work with same-cohort correctness                 | `time-study/report.json`, `time-study/pairs.json`: separate sealed cohort, same terminal outcomes, active and elapsed time, final correctness and original extraction correctness separately | Optional follow-up; deferred |
| Quantity/price/duplicate/receipt discrepancy detection and false holds   | `discrepancies/report.json`: actual detector output, category confusion matrices, labeled hard negatives, transaction denominator                                                            | 3, 4, 6 |
| Corrections and supplier-layout changes against frozen regression        | `replay/report.json`: >=3 dated meaningful revisions, before/after exact and provenance, correction events and retained correct cases                                                        | 1, 2, 6 |
| Posting correctness across supplier/rule changes                         | `posting/report.json`: independent ERP/ledger oracle, per-revision counts, all read-back mismatches, unknown/completion counts and failure-after-effect tests                                | 3, 5, 6 |
| Reproducible release                                                     | `release/report.json`: exact commit/image/config, current tests, Docker journey, rollback/recovery                                                                                           | 7       |
| Optional cloud validation                                                | `cloud/report.json` if executed; otherwise explicit skipped status                                                                                                                           | 8       |

Raw source/observations stay private when required by license/privacy; publish
sanitized aggregates and reproducible synthetic fixtures where permitted. Every
artifact binds to commit, contract, dataset/config/model hashes and date. Historical
header/draft evidence remains available under its original version. The public
case study focuses on the final validated system, not internal development history.

CV changes happen in the separate CV task after Phase 9's claim audit. A combined
time and correctness bullet uses the same time-study invoice cohort and describes
post-review correctness. Quality-holdout results remain separately identified.

The optional operator study is not a Phase 6 completion gate under contract 2.1.0.
Its timing/productivity claim remains unavailable until measured; technical quality
and posting results can be reported independently with their synthetic scope.
