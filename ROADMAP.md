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

- backend suite: 370 tests passed, 2 skipped
- frontend suite: 11 tests passed
- frontend lint and production build: passed
- backend Ruff check: passed

## Phase 0: Positioning Cleanup

Status: Next documentation-only task. It may run before provider integration.

Goal: remove historical build-log language so a new reader immediately understands the current product and its limits.

Work:

1. Rewrite public README, runbook, and demo copy around the invoice-review problem and the primary user flow.
2. Remove historical project labels and generic autonomous/back-office claims from recruiter-facing documentation.
3. State limitations plainly: local demo, no customer validation, and no unmeasured claims of accuracy, time savings, or cost reduction.

Exit criteria:

- a reader understands the user, problem, workflow, and limitation from the first documentation screen
- public documentation uses the product name consistently

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
- Groq JSON extraction returned nine non-empty invoice fields with no validation issue for the sample
- processing stopped at `needs_review`; it did not auto-approve
- the reviewer queue contained the invoice and explicit approval changed it to `approved`
- the completed smoke flow recorded six audit events
- invalid credentials produced real Mistral and Groq HTTP errors classified as non-retryable
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

Status: In progress from 15 July 2026. Workflow hardening and desktop/mobile first-impression checks have started; recruiter packaging remains open.

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
