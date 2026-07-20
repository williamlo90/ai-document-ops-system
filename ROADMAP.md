# AI Document Operations System Roadmap

This is the single source of truth for product scope, validation work, and portfolio release readiness. Do not create parallel sprint plans unless a temporary implementation plan is required and linked back here.

## Product Scope

This is an invoice-review workflow for finance operations.

The core journey is:

```text
Upload invoice -> Read invoice -> Validate fields -> Reviewer decision -> Audit record
```

The product goal is not unrestricted automation. It is to make invoice review faster to inspect, safer to approve, and easier to audit.

## Current Baseline

Status: Complete for the local demo, real-provider integration, and representative synthetic evaluation.

Delivered:

- role-separated invoice upload and reviewer approval
- PDF preview with extracted invoice fields and deterministic checks
- explicit approve, reject, and correction decisions
- audit trail, protected status transitions, retry handling, and export guardrails
- local reliability and scenario-evaluation surfaces kept outside the primary user flow
- simple user-facing navigation for upload, invoices, and approvals

Latest verified baseline:

- backend suite: 435 tests passed, 2 skipped
- frontend suite: 15 tests passed
- browser E2E: 22 tests passed, 8 capture-only tests skipped
- frontend lint, dependency audit, and production build: passed
- backend Ruff and dependency audit: passed
- full-history Gitleaks, actionlint, container runtime smoke, and Trivy HIGH/CRITICAL scan: passed

## Phase 0: Positioning Cleanup

Status: Complete on 15 July 2026.

Goal: remove historical build-log language so a new reader immediately understands the current product and its limits.

Work:

1. Rewrite public README, runbook, and demo copy around the invoice-review problem and the primary user flow.
2. Remove historical project labels and generic autonomous/back-office claims from recruiter-facing documentation.
3. State limitations plainly: local demo, no customer validation, and no unmeasured claims of accuracy, time savings, or cost reduction.

Exit criteria:

- a reader understands the user, problem, workflow, and limitation from the first documentation screen
- public documentation uses the product name consistently

Observed evidence:

- README now opens with the finance-review problem, decision boundary, architecture, proof, and limitations
- PRD and architecture describe the current invoice product instead of its historical project sequence
- `PORTFOLIO_CASE_STUDY.md` separates AI work, deterministic safeguards, human authority, evidence, and limitations
- obsolete handoff, pivot, duplicate demo, and parallel UI planning documents were removed from the public artifact

## Phase 1: Real Provider Integration

Status: Complete on 15 July 2026 for the first safe provider-backed invoice flow. Broader invoice variation belongs to Phase 2.

Goal: verify that a real provider can process safe, non-sensitive invoice PDFs without changing the approved user flow.

Work:

1. Configure provider credentials locally through environment variables. Never commit credentials.
2. Verify one safe invoice end-to-end: upload, read, validation, reviewer decision, and audit record.
3. Record provider failures separately from application failures: timeout, invalid provider response, malformed PDF, and unsupported input.
4. Keep approval as a reviewer action. A high-confidence result must not silently approve an invoice.

Observed evidence:

- the committed sample invoice produced one OCR page and non-empty text through Mistral OCR
- the retired JSON extractor returned nine non-empty invoice fields with no validation issue for
  the sample
- processing stopped at `needs_review`; it did not auto-approve
- the reviewer queue contained the invoice and explicit approval changed it to `approved`
- the completed smoke flow recorded six audit events
- invalid credentials produced real OCR and retired-extractor HTTP errors classified as
  non-retryable
- configurable provider timeouts now reach both HTTP clients instead of being silently fixed at 60 seconds
- deterministic tests cover transient `429`/`5xx` classification, requeue, retry limits, and dead-letter behavior

Exit criteria:

- provider status is based on observed runtime behavior, not configuration alone
- real authentication failures are observed; transient failure and retry behavior is covered by deterministic adapter and job-lifecycle tests
- no credential or real invoice data is committed to the repository

## Phase 2: Representative Scenario Evaluation

Status: Complete on 15 July 2026 for the versioned synthetic small golden set and provider-backed application workflow. External or customer data validation remains future evidence, not a current claim.

Goal: test whether the workflow handles representative invoice variation, not just a controlled sample.

Work:

1. Build a safe, versioned evaluation set of 20-30 representative invoices.
2. Include normal and difficult cases: total mismatch, missing vendor/date, duplicate invoice, unsupported currency, low-confidence extraction, suspicious amount, approval required, and export blocked.
3. Record observed extraction, validation, decision, retry, and failure outcomes.
4. Confirm that the PDF preview is clear in the actual demo environment.

Observed evidence:

- 20 deterministic PDF fixtures cover happy paths, missing fields, validation failures, a duplicate pair, low contrast, rotation, and multiple pages
- the first real-provider run exposed three hallucinated missing fields and only 17 of 20 fully matched documents
- prompt anti-inference rules and deterministic vendor grounding removed those unsafe false positives
- the final regression matched 160 of 160 evaluated fields and 20 of 20 expected validation behaviors with no provider error
- average provider latency was 1.09 seconds per document on the final local run
- the duplicate pair was processed through the application; the second invoice received `duplicate_invoice` while the first remained clear
- the reviewer queue separated clean decisions from correction-required invoices and displayed the duplicate reason in plain language
- both the browser UI and backend block approval while error-level validation issues remain unresolved
- the in-app PDF preview rendered the tested invoice in the uploader and reviewer workflow
- these results are synthetic small-golden-set evidence, not production or customer accuracy

Exit criteria:

- results can be reproduced from committed fixtures or documented safe generation steps
- known limits and failure modes are explicit
- no business-impact claim is made without measured evidence

## Phase 3: Market Proof And Recruiter Readiness

Status: In progress from 15 July 2026. Workflow hardening, first-impression checks, recruiter evidence, and a captioned demo video are complete. An external licensed synthetic holdout was attempted, but provider availability failed its first sealed run, so external robustness remains open and is not claimed.

Goal: turn the engineering proof into a credible finance-operations case study without overstating maturity.

Work:

1. Define the user and constraint: a finance-operations reviewer handling invoice exceptions where incorrect approval or export is costly.
2. Measure and report only observed metrics: documents processed, validation failures, exceptions caught, decisions required, blocked exports, and average review steps.
3. Create `PORTFOLIO_CASE_STUDY.md` with the problem, manual baseline, system flow, AI responsibilities, deterministic safeguards, reviewer authority, outcomes, failure modes, and limitations.
4. Add a compact business-proof report or surface, kept separate from engineering reliability metrics.
5. Record a 3-5 minute demo video with one normal invoice, one exception, one blocked risky action, and the audit result.
6. Rewrite README for a five-minute recruiter scan: problem, demo flow, architecture, proof, limitations, and one-command local run.
7. Run a 60-second first-impression check: a new reader can identify the queue, open an invoice with a visible PDF, understand the reviewer decision, and see why a risky action was blocked.

Observed evidence so far:

- uploader and reviewer now show the same correction-required status for invoices with validation blockers
- invoice search now matches the filename, extracted vendor, and invoice number as promised by the UI
- status filters use distinct business labels instead of duplicate or unreachable options
- approved invoice data is immutable through the intake draft API; edits require a new review cycle rather than silently changing approved evidence
- desktop and 390 px mobile browser checks cover uploader list, reviewer queue, PDF detail, and blocked approval
- the mobile reviewer queue was corrected from an overlapping wide table into readable tabs and single-column review cards
- recruiter-facing README, case study, reliability report, and 3-5 minute demo script now tell one bounded product story
- a 3:37 captioned MP4 demonstrates clean approval and duplicate blocking with committed synthetic PDFs through a deterministic UI contract harness
- a compact recruiter evidence pack separates observed engineering proof from unmeasured business impact
- a non-technical matrix maps all 20 scenarios to the business risk, expected safeguard, and observed result
- the completed-decision UI shows actor, timestamp, audit-event count, and export eligibility next to the invoice
- public artifact packaging now requires the case study and excludes obsolete historical planning documents
- a private 25-invoice FATURA pack now separates 15 diagnostic cases from 10 checksum-sealed holdout cases across five scan-quality profiles
- diagnostic iteration reached 93.33% end-to-end field accuracy; all 14 provider-successful documents matched every evaluated field and validation outcome
- the first sealed holdout recorded only 1 of 10 provider-successful documents because nine requests ended in `extractor_http_error` after bounded backoff
- the failed holdout is published as a 10% end-to-end result rather than being rerun or reframed as conditional accuracy; external robustness remains unproven
- raw external documents, labels, OCR, and provider responses remain outside Git; only sanitized aggregate evidence is public
- the complete claim boundary and aggregate results are recorded in [External Invoice Evaluation V1](docs/external-invoice-evaluation-v1.md)
- reviewer correction requests now route to the uploader and return to the reviewer after a changed field is submitted
- every correction retains the original AI output, sequential before/after values, actor, reason, timestamp, and field-level diff in append-only storage
- raw correction datasets export only to a private or Git-ignored path; public evidence contains aggregate counts without invoice values or identities
- the deterministic correction contract passes all 6 lineage, no-op, reason carry-forward, and privacy checks documented in [Reviewer Correction Feedback](docs/reviewer-correction-feedback.md)

### Security Gate Before Provider Replacement

Status: SEC-001, SEC-002, SEC-004, SEC-005, SEC-006, SEC-007, SEC-008, SEC-009, and SEC-010 have
application-level remediation on 19 July 2026. The SEC-003 production ClamAV boundary and SEC-005
provider endpoint boundary are implemented and test-covered; scanner deployment,
provider-contract verification, hosted infrastructure verification, and independent review remain
gates.

- [Security And Privacy Assurance V1](docs/security/security-assurance-v1.md) records the threat model, provider data boundaries, verified controls, and residual risk
- [Security Evidence And Traceability V1](docs/security/security-evidence-v1.md) binds the commands, candidate, results, and unrun checks
- [Security Remediation V1](docs/security/security-remediation-v1.md) records the hosted-policy and server-owned identity changes and executed regression evidence
- [Security Remediation V2](docs/security/security-remediation-v2.md) records upload scanning, private-cache headers, retention purge, and residual infrastructure gates
- [Security Remediation V3](docs/security/security-remediation-v3.md) records provider HTTPS/allowlist enforcement, redirect refusal, and the remaining provider-governance decision
- [Security Remediation V4](docs/security/security-remediation-v4.md) records the durable accounting-delivery ledger, replay behavior, and ambiguous-result reconciliation path
- [Security Remediation V5](docs/security/security-remediation-v5.md) records the untrusted-OCR prompt boundary, evidence requirements, adversarial tests, and approval blocker
- [Security Remediation V6](docs/security/security-remediation-v6.md) records hash-locked dependencies, immutable CI references, advisory gates, image hardening, and scan evidence
- [Security Remediation V7](docs/security/security-remediation-v7.md) records dedicated metrics authentication, hosted credential policy, and negative-route evidence
- [Security Hardening Completion Audit](docs/security/security-completion-audit.md) records the final application finding closure, release decision, executed gates, and exact external blockers
- [Supply-Chain Controls](docs/security/supply-chain.md) records lock regeneration, verification, and dependency-update policy
- [Provider Data Boundary](docs/security/provider-data-boundary.md) records exactly what is sent to each provider and what remains prohibited
- the loopback-only synthetic demo is `PASS_WITH_LIMITATIONS`
- a controlled single-workspace hosted demo is `PASS_WITH_LIMITATIONS`; untrusted uploads and real-data use remain blocked by the other open findings
- provider replacement must be evaluated against HTTPS/host restrictions, ZDR and retention, data location, DPA terms, quota stability, and deletion responsibilities

Remediation order:

1. [x] Make every hosted mode enforce strong token, cookie, CSRF, and API-documentation policy.
2. [x] Replace caller-asserted role/workspace headers with server-owned principal sessions.
3. [x] Add the production ClamAV adapter, sensitive-response no-store policy, and explicit retention/deletion; verify the scanner service and infrastructure lifecycle in the authorized deployment.
4. [x] Add durable outbound idempotency with crash-safe replay and reconciliation evidence.
5. [x] Add adversarial invoice prompt-injection tests and consequence-blocking evidence.
6. [x] Pin and scan the dependency, CI action, and release-image supply chain.
7. [x] Enforce provider HTTPS, exact-host allowlists, and redirect refusal; replacement-provider research remains gated by the documented data-governance acceptance criteria.
8. [x] Protect internal metrics with a dedicated service credential and private cache policy.
9. [x] Repeat all locally executable checks and record the completion audit.
10. [ ] Obtain an independent review and verify the external deployment gates before making a hosted security claim.

Positioning rule:

> AI Document Operations System with evidence-bound extraction, deterministic validation, approval-gated execution, and an auditable review trail.

Do not lead with historical project labels, generic platform wording, or autonomous-operation claims.

Exit criteria:

- a recruiter can understand the problem, safeguard, and evidence without reading source code
- screenshots and video show real PDF rendering and observed outcomes
- all README and case-study claims link to documented evidence
- the primary UI passes the 60-second first-impression check without explanation

## Phase 4: Release Readiness

Status: Starts after Phase 3.

Goal: publish a clean, reproducible portfolio artifact.

Work:

1. Run backend tests, frontend tests, lint, production build, and artifact hygiene checks.
2. Verify that `.env`, private invoices, uploads, caches, local databases, and generated runtime files are excluded.
3. Confirm the documented local run path works from a clean clone.
4. Freeze the demo script, screenshots, case study, and evidence summary together.
5. Remove deliberately hidden legacy detail views and split `frontend/src/App.tsx` in an isolated, behavior-preserving refactor covered by end-to-end tests.

## Guardrails

- Do not add another document type before invoice real-data evaluation is complete.
- Do not add broad dashboards or new autonomy features before market-proof work is complete.
- Do not claim production readiness, customer validation, time savings, cost savings, or accuracy without measured evidence.
- Preserve explicit reviewer approval for consequential actions.
- Keep technical reliability surfaces available for evidence, but outside the primary user workflow.

## Definition Of Done

This portfolio release is complete when:

- a real provider has been tested with a representative safe dataset
- extraction and validation limits are documented
- approval and blocked-action behavior are demonstrated
- case study, README, architecture diagram, and demo video tell one consistent story
- the repository is clean, reproducible, and free of credentials or real sensitive documents
