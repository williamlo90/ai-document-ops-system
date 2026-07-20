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

### Product UI Redesign Loop

Status: Complete on 20 July 2026 for the current uploader, reviewer, and monitoring surfaces.

Goal: make the product feel like one calm finance-operations application while preserving the
existing upload, review, approval, correction, monitoring, and audit behavior.

Design direction:

- use a restrained invoice-management shell for navigation and document lists
- use a focused split workspace for PDF review and reviewer decisions
- use an evidence-first analytics layout for monitoring, with technical diagnostics disclosed only on demand
- prefer plain business language, clear status hierarchy, and one obvious next action per screen

Implementation loop:

1. Establish shared visual tokens, spacing, typography, navigation, buttons, and status treatments.
2. Rebuild invoice lists as the primary work surface instead of a collection of equal-weight cards.
3. Simplify the review workspace around the PDF, extracted values, blockers, and one decision area.
4. Put monitoring conclusions, sample size, and provider cost before detailed diagnostics.
5. Verify desktop and mobile screenshots, keyboard focus, text fit, loading, empty, and error states.
6. Repeat visual inspection and usability fixes until no material first-impression issue remains.

Exit criteria:

- uploader, reviewer, and administrator surfaces look like one product
- the main business action can be identified within five seconds on every primary screen
- technical evidence remains available without competing with invoice work
- desktop and mobile browser captures have no clipping, overlap, unreadably small text, or blank PDF state

Observed evidence:

- uploader, reviewer, and administrator now share one light finance-operations shell with literal document iconography and restrained status colors
- approvals and invoice libraries use scan-friendly rows with one primary action instead of floating card-heavy composition
- the reviewer workspace keeps the invoice PDF and decision evidence side by side on desktop, while mobile caps the scrollable PDF so the decision remains reachable
- monitoring opens with provider calls, evaluated invoices, stored runs, and known weak spots; run-level diagnostics are available through progressive disclosure
- monitoring tabs use in-app history navigation without full-page refresh and remain directly reachable for administrators
- browser inspection confirmed rendered PDF content, working monitoring disclosure, no page-level horizontal overflow, and no browser console errors
- frontend unit tests pass 15 of 15; browser tests pass 22 with 8 capture-only tests skipped across desktop, tablet, and mobile
- automated accessibility checks report no serious or critical violations on the intake screen across all three viewports

### Client-Deliverable SaaS UI Conversion

Status: Per-page implementation planning complete on 20 July 2026. Eight of nine target pages
have replacement visual references and motion specifications. Settings remains design-gated.

Goal: evolve the working invoice application into a cohesive, client-deliverable finance
operations product with distinct business capabilities and a consistent application shell.

The visual source of truth, page sequence, and design contract are recorded in
[`docs/ui-redesign-reference.md`](docs/ui-redesign-reference.md). Generated numbers, AI findings,
uptime percentages, destination names, and activities are layout examples rather than product
claims. The page-specific motion specification corrects any unsafe or internally inconsistent
example in its paired image.

This roadmap remains the only sprint-plan source of truth. The implementation uses complete
vertical page sprints rather than a growing sequence of mini sprints.

#### Implementation Authority

When sources disagree, use this order:

1. Backend authorization, security, approval, idempotency, and audit boundaries.
2. Page-specific motion and interaction specification.
3. Saved visual reference for layout, density, typography, spacing, and visual hierarchy.
4. Existing frontend behavior and component patterns.

The target is a close structural and visual match at the `1536 x 1024` reference viewport, not a
literal copy of mock values. Real data may change row content and counts. Known reference issues,
including contradictory export eligibility and incorrect System flow percentages, must not be
implemented.

#### Page Sprint Protocol

Every page sprint follows the same gates:

1. **Study the reference:** annotate shell, grid, dimensions, hierarchy, controls, states, and
   responsive implications from the saved PNG.
2. **Study the specification:** convert every required motion, focus, keyboard, loading, empty,
   error, reduced-motion, and responsive behavior into a page checklist.
3. **Map the capability:** classify each visible element as existing backend support, frontend
   derivation, backend delta, or unsupported concept that must be hidden.
4. **Freeze the contract:** define typed request and response shapes and add backend contract
   tests before wiring new data.
5. **Implement the page:** use live application data, shared design primitives, URL state, and
   server-assigned role boundaries.
6. **Implement all states:** loading, empty, partial error, full error, success, pending,
   keyboard focus, touch fallback, and reduced motion.
7. **Verify behavior:** run focused backend, frontend, accessibility, and browser tests.
8. **Verify appearance:** capture `1536 x 1024`, `1280 x 800`, `1024 x 768`, and `390 x 844`;
   compare the desktop capture with the reference using overlay and image diff, then inspect all
   sizes for clipping, overflow, and task reachability.
9. **Approval gate:** present the implementation screenshot and documented deviations. Do not
   begin the next page until the current page is accepted.
10. **Document the sprint:** commit and push the complete vertical slice with a page-specific
    message such as `feat(ui): implement invoices reference`.

Internal backend or refactor checkpoints do not become separate named sprints.

#### Audited Baseline

Current reusable foundations:

- React, TypeScript, TanStack Query, Lucide icons, PDF.js, Vitest, Playwright, and axe checks
- authenticated PDF rendering and invoice upload
- invoice listing, workflow projection, correction capture, reviewer queue, save, approve,
  reject, correction request, escalation, audit events, retry, and reprocess
- provider and integration status, operational jobs and retry, notifications, metrics summary,
  evaluation records, and provider-cost evidence

Current structural constraints:

- most frontend behavior remains concentrated in `frontend/src/App.tsx`
- navigation uses a custom History API screen state rather than a route tree
- no chart library is installed for accessible interactive charts
- Exceptions has no dedicated paginated read model
- Exports supports file download and single-document controlled delivery, not the designed batch,
  draft, history, or scheduling workflow
- Evaluation APIs do not yet expose the designed invoice-quality run model
- System has current status and jobs but no measured seven-day uptime or consistent stage-flow
  aggregate
- business Settings are environment-driven and not writable through an audited workspace API

#### Role Matrix

- **Uploader:** upload through Invoices and inspect only invoices they submitted. No reviewer,
  evaluation, system, export, or settings controls.
- **Reviewer:** Overview, permitted invoice inspection, Review Queue, Invoice Review Workspace,
  and Exceptions. Export access requires an explicit server permission.
- **Administrator:** all pages, subject to the same approval and export guardrails.
- Navigation visibility is derived from the server session. The client never offers a role
  switcher or treats hidden navigation as authorization.

#### Sprint UI-00: Shared Foundation

Status: Complete on 2026-07-20. The route tree, role guards, shared shell, visual tokens,
responsive states, reduced-motion handling, and shared primitives are active.

Goal: create the stable system needed to reproduce the references without changing business
behavior.

Work:

1. Introduce a proper client route tree for Overview, Invoices, Review Queue, Invoice Review,
   Exceptions, Exports, Evaluation, System, and Settings, including deep links and browser-back
   behavior.
2. Split new work into application shell, page, feature, API, and shared component boundaries;
   do not add more page logic to the existing monolith.
3. Implement the shared shell, top bar, role-filtered navigation, typography, color, spacing,
   border, shadow, status, focus, and reduced-motion tokens from the references.
4. Build shared primitives only where repeated: page header, KPI strip, filter toolbar, data
   table, status badge, tooltip, drawer, modal, toast, skeleton, empty state, and error state.
5. Use CSS transitions for the prescribed motion. Add no general animation dependency unless a
   page proves CSS insufficient.
6. Select one maintained chart library for Overview and Evaluation rather than hand-rolling
   chart interaction, keyboard semantics, and tooltips.
7. Add reference-viewport screenshot projects and image-diff artifacts to Playwright without
   turning dynamic text into brittle pixel assertions.
8. Preserve the current uploader and reviewer flows with regression tests before page migration.

Exit criteria:

- all target routes render inside one matching shell without full-page refresh
- role navigation and direct-route guards are tested
- shared primitives have focus, reduced-motion, loading, and error behavior
- existing invoice upload and reviewer-decision flows still pass before the first page migration

#### Sprint UI-01: Invoices

Status: Complete on 2026-07-20. The live invoice library, server-side summary and filters,
inspection panel, upload action, URL state, and role boundaries replaced the legacy screen.

References:

- `docs/assets/ui-reference/modern-operations-invoices.png`
- `docs/ui-motion-specs/invoices-motion-spec.md`

Frontend scope:

- searchable, filterable, paginated invoice library with URL state
- summary metrics and AI insight strip based only on observed records
- inspection-only right panel with validation summary, PDF preview, and Open invoice action
- role-aware Upload invoice action; no approval controls on this page

Backend mapping:

- reuse `GET /invoices`, `GET /invoices/{id}/workflow`, document content, and upload endpoints
- extend invoice summaries with invoice number, invoice and due dates, last update, reviewer or
  owner, and export state where available
- add explicit vendor, invoice-date, sort, and business-status query contracts rather than
  filtering a full result set in the browser
- aggregate summary and insight counts on the server so pagination does not corrupt totals

Exit criteria:

- uploader sees only permitted invoices; reviewer and administrator access follows server policy
- selection, filters, pagination, deep link, PDF loading, and partial errors match the spec
- reference comparison passes before Review Queue begins

#### Sprint UI-02: Review Queue

References:

- `docs/assets/ui-reference/modern-operations-review-queue.png`
- `docs/ui-motion-specs/review-queue-motion-spec.md`

Frontend scope:

- queue KPIs, search, filters, sorting, pagination, selected-row state, and fixed inspector
- confidence and risk explanations grounded in stored extraction and validation data
- inspection and recommendation context without duplicating the full decision workspace

Backend mapping:

- reuse `GET /review/queue`, invoice workflow projection, work-item ownership, validation issues,
  and extraction confidence
- evolve the queue into a paginated/filterable read model containing blocker summary, risk,
  confidence, owner, due information, and selected-invoice detail keys
- derive risk deterministically from validation and configured policy; do not invent SLA or due
  dates when no policy exists
- add assignment only by reusing or extending audited work-item ownership

Exit criteria:

- queue count and rows are sourced from the same filtered contract
- changing rows updates the inspector in place and preserves URL and scroll state
- keyboard navigation, touch drawer, loading, empty, and error states are verified

#### Sprint UI-03: Invoice Review Workspace

References:

- `docs/assets/ui-reference/modern-operations-invoice-review-workspace.png`
- `docs/ui-motion-specs/invoice-review-workspace-motion-spec.md`

Frontend scope:

- three-column PDF, extracted-data, and decision workspace
- inline editing with local focus, save, revalidation, evidence disclosure, and line items
- required notes, confirmation dialogs, submission lock, outcome toast, and audit consequence
- field-to-document highlighting only when reliable source coordinates exist

Backend mapping:

- reuse workflow detail, authenticated PDF, `POST /review/{id}/save`, approve, reject, correction,
  correction history, validation, and audit events
- enforce correction and rejection note requirements on the server, not only in the form
- preserve backend approval blocking while error-level validation issues remain
- extend extraction evidence with page coordinates only if providers or deterministic PDF text
  mapping can supply reliable values; never guess a highlight location
- return the saved decision, actor, timestamp, audit result, and export eligibility in one
  post-decision response or immediate refetch contract

Exit criteria:

- edits survive validation and errors without losing the note
- duplicate decisions are prevented and forbidden transitions remain `409`
- PDF controls, decision keyboard flow, focus return, and reduced motion match the specification

#### Sprint UI-04: Exceptions

References:

- `docs/assets/ui-reference/modern-operations-exceptions.png`
- `docs/ui-motion-specs/exceptions-motion-spec.md`

Frontend scope:

- workload summary, issue categories, URL-backed filters, paginated master-detail table,
  assignment, related checks, and navigation into Invoice Review
- no note-only resolution path for deterministic blockers

Backend mapping:

- create a dedicated Exceptions read model derived from validation issues, workflow projection,
  document status, and owner rather than recomputing it independently in the frontend
- provide summary, paginated list, detail, assignment, and authorized export-list contracts
- define due and SLA fields only after a real policy source exists
- mark a blocker resolved only after revalidation clears it; any future override requires server
  authorization, reason, and immutable audit evidence

Exit criteria:

- category, KPI, table, and detail counts reconcile
- filter and selected exception survive refresh and browser back
- assignment, partial-detail error, keyboard navigation, and validated resolution are tested

#### Sprint UI-05: Exports

References:

- `docs/assets/ui-reference/modern-operations-exports.png`
- `docs/ui-motion-specs/exports-motion-spec.md`

This is a larger page sprint because its designed workflow does not yet exist as a complete
backend domain.

Frontend scope:

- eligible invoice selection, batch summary, eligibility checks, destination and format,
  drafts, run history, execution state, and failure recovery
- schedule controls only when scheduling is actually implemented
- configured destination names only; never hard-code NetSuite as a working integration

Backend mapping:

- preserve current CSV/JSON download and single-document controlled delivery
- add persistent export batches, selected invoice membership, destination capability, eligibility
  result, idempotency key, run state, result, and audit history
- expose eligible list, create/update draft, execute, run list/detail, and retry contracts
- add scheduling only if a persistent scheduler, cancellation, worker execution, restart recovery,
  authorization, and audit tests are included; otherwise the final page uses Create export or
  Save draft instead of Schedule tomorrow
- never mark invoices exported until the delivery or file-generation boundary confirms success

Exit criteria:

- contradictory eligibility states cannot be represented by the API schema
- duplicate and partial exports are blocked or reconciled deterministically
- a failed run preserves the batch and never marks invoices exported
- the UI is visually approved with the documented action-label deviation when scheduling is absent

#### Sprint UI-06: Evaluation

References:

- `docs/assets/ui-reference/modern-operations-evaluation.png`
- `docs/ui-motion-specs/evaluation-motion-spec.md`

Frontend scope:

- honest verdict, run selector, quality trend, regression summary, field comparison, scenario
  coverage, limits, cost, and recent runs
- accessible chart tooltips, point selection, range selection, URL state, and run drawers

Backend mapping:

- reuse stored scenario evaluations, provider-cost evidence, dataset contracts, and existing
  evaluation services where their semantics match
- create a dedicated invoice-evaluation run contract with dataset version, valid completion,
  field denominator, field and validation matches, configured gates, regression tolerance,
  scenario coverage, failure taxonomy, duration, usage, and estimated cost
- persist attempts separately from valid comparison runs
- expose start and observed stage progress only if the evaluation runs through an actual job;
  otherwise use a pending request state without fabricated percentages

Exit criteria:

- verdict, regression counts, field rows, chart, and denominator reconcile exactly
- synthetic and small-sample limitations remain visible
- failed attempts do not replace the latest valid run
- cost remains labelled as an estimate and links to recorded usage evidence

#### Sprint UI-07: System

References:

- `docs/assets/ui-reference/modern-operations-system.png`
- `docs/ui-motion-specs/system-motion-spec.md`

Frontend scope:

- overall health, KPI strip, status/processing/integrations/audit tabs, service detail, attention,
  processing flow, recent jobs, retry, maintenance, and partial errors
- sanitized operational details rather than raw engineering logs

Backend mapping:

- reuse metrics summary, provider health, integration status and test, operational jobs and retry,
  notifications, audit export, and readiness checks
- add one System status read model with observation time, freshness, service state, active and
  waiting counts, and recent job summaries
- calculate stage flow from one defined cohort and denominator; do not copy sample percentages
- show uptime only after persisted health snapshots can support the requested window; otherwise
  show current status and `Not enough history`
- sanitize failure details and authorize logs, retries, and configuration links separately

Exit criteria:

- degraded services do not make healthy capabilities appear unavailable
- missing telemetry becomes Unknown, never zero or Operational
- retries update attempts only after acceptance and preserve failed evidence
- stage counts and percentages are covered by deterministic aggregation tests

#### Sprint UI-08: Overview

References:

- `docs/assets/ui-reference/modern-operations-overview.png`
- `docs/ui-motion-specs/overview-motion-spec.md`

Overview is intentionally implemented after its source pages so every metric and deep link uses
the finalized business definitions.

Frontend scope:

- urgent-work briefing, KPI row, AI findings, alerts, decision queue, throughput, exception
  breakdown, pipeline, and recent decisions
- every card or chart links to the corresponding filtered page

Backend mapping:

- create a business-facing Overview read model that composes finalized invoice, review,
  exception, export, and audit definitions
- reuse metrics and notifications, but calculate trend windows and recent decisions server-side
- label AI findings only when they come from stored validation or extraction evidence; ordinary
  deterministic aggregates are not presented as AI discoveries

Exit criteria:

- every count reconciles with its destination page and time window
- no dashboard number is hard-coded or calculated from only the current page of results
- charts and tooltips remain usable with reduced motion, keyboard, touch, and narrow viewports

#### Sprint UI-09: Settings

Status: blocked by design input, not by implementation difficulty. The current Settings image is
only a concept and has no replacement redesign or motion specification.

Before implementation:

1. Receive and approve the Settings redesign reference.
2. Receive and reconcile its page-specific motion and interaction specification.
3. Define the supported scope against the current authentication model.

Likely backend delta:

- persistent audited workspace profile and business review preferences
- notification preferences and retention settings within server policy bounds
- read-only environment and integration summaries with no secret values
- Team and roles remain hidden until the product has a real persisted user and authorization
  model; static access tokens are not presented as team management

Exit criteria follow the same page sprint protocol and require server-side validation and audit
for every writable setting.

#### Sprint UI-10: Integration, Cleanup, And Release Gate

Work:

1. Run complete backend, frontend, lint, build, dependency, security, browser, accessibility, and
   visual suites.
2. Exercise uploader, reviewer, and administrator journeys from a clean seeded state.
3. Verify direct routes, refresh, browser back, URL filters, session expiry, partial network
   failures, and recovery.
4. Remove superseded frontend screens, CSS, types, queries, and tests only after the replacement
   path is covered.
5. Remove backend endpoints or modules only when no frontend, documented workflow, test, or
   external contract uses them.
6. Re-run desktop, tablet, and mobile screenshot inspection for all pages.
7. Update demo video, screenshots, case study, and release evidence from the final application.

Exit criteria:

- no legacy UI route competes with the new product routes
- no dead control, mock metric, unsupported integration, or hidden authorization bypass remains
- every primary page has an approved screenshot and recorded backend contract
- worktree is clean and the release commit is pushed

Program exit criteria:

- every primary capability has an approved screen and an obvious user purpose
- implemented pages match the approved references in structure, density, hierarchy, and state treatment
- no mock metric, finding, activity, confidence value, or business claim ships as live data
- existing invoice workflow and security boundaries remain covered by automated tests

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
