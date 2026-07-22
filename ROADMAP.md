# Invoice Review Roadmap

This file is the single source of truth for planned product work. Historical implementation plans,
UI concept handoffs, and security remediation diaries are intentionally excluded.

## Product Outcome

Build an invoice-review application that a non-technical finance user can understand without an
explanation and that a technical evaluator can inspect without weakening business safeguards.

The core journey is:

```text
Upload -> Check source and fields -> Resolve blockers -> Decide -> Export approved records
```

## Non-Negotiable Controls

1. Extraction confidence never grants approval.
2. Error-level validation blocks approval in the UI and API.
3. Approval, rejection, and correction are explicit human decisions.
4. Corrections retain the original value, updated value, actor, reason, and timestamp.
5. Terminal decision and export evidence is append-only from the application workflow.
6. Roles and workspace membership are derived and enforced by the server.
7. Export requires approval, idempotency, and failure-aware retry behavior.

## Completed Product Refactor

### Phase 0: Baseline And Guardrails

- Recorded backend, frontend, lint, build, and browser baselines.
- Captured the safety invariants above before changing the interface.
- Added the restrained invoice-product direction to this roadmap.

### Phase 1: Remove Template Signals

- Removed decorative AI labels, recommendations, green overall confidence, dead utility controls,
  automatic first-row selection, and decorative page motion.
- Kept functional drawers, modals, toasts, loading indicators, and reduced-motion behavior.

### Phase 2: Information Architecture

- Primary navigation is now Inbox, Invoices, and Exports.
- Quality and Operations are grouped under Admin.
- Legacy URLs redirect to the relevant current view while preserving useful query state.

### Phase 3: Daily Work

- Inbox combines decision work and blocking issues through two state tabs.
- Invoices uses lifecycle tabs and keeps the table as the primary surface.
- Details open only after a deliberate user selection.

### Phase 4: Review And Export

- Review places the source PDF beside fields, checks, and an explicit decision area.
- Export shows eligibility and batch controls only when a selection or existing batch requires them.
- Approval, blocker, retry, and idempotency contracts remain backend-enforced.

### Phase 5: Administrator Evidence

- Quality is limited to labeled-test results, field performance, scenario coverage, and honest limits.
- Operations prioritizes unresolved alerts, failed jobs, retries, service status, and audit records.
- Duplicate KPI, chart, funnel, and side-rail surfaces were removed.

### Phase 6: Repository Hygiene

- Removed inactive page implementations and unused frontend dependencies.
- Split the monolithic stylesheet by responsibility and added a readable typography floor.
- Consolidated product documentation around the Invoice Review identity.
- Removed superseded UI concepts, motion handoffs, old screenshot matrices, and remediation diaries.

## Completed Finishing Gate

- 453 backend tests passed with 2 skipped; Ruff check and format passed.
- 13 frontend tests, lint, production build, and dependency audit passed.
- 25 active product and workflow browser tests passed across desktop, tablet, and mobile.
- Inbox, Invoices, Review, Exports, Quality, and Operations passed serious-accessibility and page
  overflow checks at every tested viewport.
- The current screenshot matrix and 84-second captioned demo were regenerated and visually
  inspected, including rendered PDF frames.
- The release record for this phase is the commit containing these results and its passing CI run.

## Next Evidence Phase

After the thesis defense and before processing real client data:

1. Validate 25 private, legally usable invoices that are excluded from Git.
2. Maintain versioned golden labels and an experiment log for accuracy, latency, provider errors,
   and estimated cost.
3. Exercise messy scans, rotations, multiple pages, totals, currencies, duplicates, and missing data.
4. Verify reviewer corrections and failure taxonomy against those cases.
5. Complete the external provider, retention, scanner, and privacy acceptance gates documented in
   the security posture.
6. Record a hosted or one-command recruiter demo only after the seeded local flow is stable.

## Deliberately Deferred

- a second document type;
- payment execution;
- chatbot or document Q&A;
- production multi-tenancy and billing;
- live ERP delivery without an approved integration boundary;
- claims about customer impact, time savings, or production accuracy without observed evidence.
