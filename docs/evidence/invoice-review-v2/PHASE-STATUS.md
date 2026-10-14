# Phase status and learning checkpoints

Updated 2026-10-14. One completed phase = one commit, then push to `origin/main`.
Do not publish a success checkpoint until its gate passes. Local plan remains ignored.

| Phase | Status                                               | Exit evidence                                          |
| ----- | ---------------------------------------------------- | ------------------------------------------------------ |
| 0     | Published: 3d36ac3                                   | Contracts, schema validation and erp-capabilities.json |
| 1     | Published: 672a71a | PHASE-1.md and actual OCR.space diagnostic                   |
| 2 | Published: 1c7cfd3 | PHASE-2.md and phase2-validation.json; later live ERP/PostgreSQL checks retained locally |
| 3 | Gate passed; single phase-3 checkpoint | PHASE-3.md and phase3-validation.json; live draft ERP read, SQLite/PostgreSQL matching |
| 4 | Gate passed; single phase-4 checkpoint | PHASE-4.md and phase4-validation.json; SQLite/PostgreSQL exception workflow |
| 5 | Gate passed; single phase-5 checkpoint | PHASE-5.md and phase5-validation.json; synthetic sandbox draft, submit and ledger read-back |
| 6     | Not started                                          | Frozen quality/time/revision evidence                  |
| 7     | Not started                                          | Docker and release checks                              |
| 8     | Optional, not started                                | Default skip unless needed                             |
| 9     | Not started                                          | Public proof and CV claim mapping                      |

## Phase 0 gate checklist

- Baseline reconciled; archived work preserved and all 17 hashes verified: pass.
- Scope, outcomes and authority boundaries defined: pass.
- Metric numerators/denominators, failure treatment and thresholds frozen: pass.
- Dataset split protocol, planned manifest and schema prepared: pass.
- CV claim evidence paths and future producing phases assigned: pass.
- Sandbox actual API/permissions/record capability check: pass; access limitations recorded as Phase 2/5 prerequisites.
- Overall phase: **gate passed**. This phase is published as one `phase-0:` commit; use Git history for its SHA and delivery status.

## Learning checkpoint

The problem is defining what success means before implementing more automation.
Header accuracy, whole-invoice correctness, safe decisions, verified posting and
workflow time have different denominators and must not share an ambiguous score.
Read-back proves more than an HTTP success, but also needs an independent oracle.
Separate quality and time-study cohorts avoid operator familiarity contaminating
the time/quality claim. Unknown remote outcomes need explicit state and recovery.

No product behavior changed in Phase 0. Changes are the local-plan ignore rule and
the contracts in this directory. Validation checks schema shape, manifest consistency,
links and Git diff hygiene; this is not production-grade runtime verification.
The next phase is Phase 1: selectively reuse the archived evaluator, align it with
this contract, and separate mutation evidence from actual-provider diagnostics.
Phase 0 does not certify ERP posting or production readiness.
