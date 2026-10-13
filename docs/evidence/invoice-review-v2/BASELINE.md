# Phase 0 baseline inventory

Inspected 2026-10-13, `main` at `83ffd12`; remote `origin/main` matched that SHA.
Only pre-existing tracked diff was the user-requested local-plan `.gitignore` rule.
No repository AGENTS.md was found in the repository inventory; chat instructions apply.

| Capability                                | Status                    | Inspected source and delta                                                                                                            |
| ----------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| PDF/OCR/extraction and provider benchmark | Existing                  | `backend/app/benchmark/service.py` serializes eight header fields only; line items are dropped from scoring input                     |
| Header evaluator                          | Existing, limited         | `backend/app/evaluation/invoice.py`: eight fields; old results remain header-only                                                     |
| Failure scoring                           | Needs repair              | `external_holdout.py::_validation_metrics` compares default empty sets without requiring completed observation                        |
| Line schema                               | Partial                   | `extraction/schemas.py`: description/quantity/unit_price/amount; no UOM, stable line ID or revision provenance                        |
| Correction history                        | Existing foundation       | `review/models.py`: original/before/after, actor/time/reason; extend field evidence and layout replay                                 |
| Approval                                  | Partial                   | `review/services.py`: checks current validation; no PO/receipt/policy/mapping snapshot binding                                        |
| Procurement and matching                  | Missing                   | No complete authoritative PO/receipt entities, allocations or deterministic three-way workflow                                        |
| ERP draft delivery                        | Existing                  | `erpnext_adapter.py`: explicitly requires docstatus 0; mapping uses benchmark constants                                               |
| Recovery                                  | Existing foundation       | `delivery_executor.py` and `integrations/models.py`: payload hash, pending/failed/unknown and reconciliation; submit operation absent |
| UI                                        | Existing foundation       | ReviewWorkspacePage, ExportsPage and QualityAnalysis: review, draft delivery, header metrics; no transaction matching UI              |
| Persistence                               | Existing foundation       | `documents/sqlite_schema.py`, PostgreSQL migrations 001–004; new changes must be additive and tested on both                          |
| Actual current sandbox capability         | Verified with access gaps | Draft read/create allowed; PO/receipt/GL read and submit denied; see ERP-PREFLIGHT                                                    |

## Archived work, not active code

The incoming local spec predates the user's archive decision. Its statement that
evaluator V2 is active/uncommitted is superseded by this reconciliation.
Archive name: `ai-document-phase1-2026-10-13`, stored outside this repository.
All 17 archived files passed SHA-256 verification against its manifest today.
The archive contains ten modified source/data files, six new files (including the
old domain plan), and a test log. No archived code has been restored in Phase 0.

Partial work available for Phase 1: line scorer, whole-invoice metrics, failure
handling, serializer, Quality UI, regression tests and mutation runner. Missing
relative to the new contract: UOM/provenance scoring, ambiguity policy alignment,
layout/correction timelines, actual-provider diagnostic and final verification.
Reuse selectively after reviewing the archived diff; do not replay the entire
patch over newer work. Preserve original archive and all V1 evidence.

The archived 20-document/22-line mutation report measures the evaluator, not OCR
quality. Its previous tests are historical, not validation of this Phase 0 tree.
README's 79/80 score is header accuracy; 68% timing measures verified draft elapsed
time on six invoices, not posting or active handling time.
