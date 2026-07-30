# Invoice Review Roadmap

This roadmap tracks the product work that still matters. Superseded implementation plans and old UI
handoffs are not kept here.

## Product goal

Build an invoice-review application that a finance user can understand without a walkthrough and
that a technical reviewer can inspect without weakening approval and export controls.

```text
Upload -> Check source and fields -> Resolve blockers -> Decide -> Export approved records
```

## Rules that must stay true

1. Extraction confidence never grants approval.
2. Validation errors block approval in the UI and API.
3. Approval, rejection, and correction are explicit human actions.
4. Corrections keep the original value, updated value, actor, reason, and timestamp.
5. Final decisions and export records are append-only in the application workflow.
6. The server enforces roles and workspace membership.
7. Export requires approval, idempotency, and failure-aware retry behavior.

## Completed work

### Baseline and safety checks

- Recorded backend, frontend, lint, build, and browser baselines.
- Captured the workflow rules above before changing the UI.
- Narrowed the product to one complete invoice journey.

### Product cleanup

- Removed labels, recommendations, confidence indicators, utility controls, and animations that did
  not help reviewers complete a task.
- Kept functional drawers, modals, toasts, loading states, and reduced-motion behavior.

### Navigation

- Made Inbox, Invoices, and Exports the primary navigation.
- Grouped Quality and Operations under Admin.
- Kept redirects for old URLs while preserving useful query parameters.

### Daily review work

- Split Inbox into invoices waiting for a decision and invoices blocked by an issue.
- Added lifecycle tabs to Invoices and kept the table as the main surface.
- Removed automatic first-row selection. Details open only after the user selects an invoice.

### Review and export

- Placed the source PDF beside editable fields, validation results, and decision controls.
- Showed export eligibility and batch controls only when they are needed.
- Kept approval, blocker, retry, and idempotency rules enforced by the backend.

### Administrator views

- Limited Quality to labeled results, field performance, scenario coverage, and limitations.
- Made unresolved alerts, failed jobs, retries, service status, and audit records the focus of
  Operations.
- Removed duplicate KPIs, charts, funnels, and side panels.

### Repository cleanup

- Removed inactive pages and unused frontend dependencies.
- Split the large stylesheet by responsibility and added a readable typography floor.
- Consolidated documentation around the Invoice Review product.
- Removed old UI concepts, motion handoffs, screenshot matrices, and remediation diaries.

### Maintainability and bounded reads

- Split backoffice planning, execution, and recovery while preserving the service API.
- Split export eligibility, execution, and workspace projection while preserving transaction
  ownership and response contracts.
- Separated SQLite connection/transaction ownership from schema and migration setup.
- Expanded Mypy from the original selective scope to the transaction, ownership, worker,
  persistence, query, and composition modules changed by this hardening pass.
- Replaced full collection scans in metrics, provider health, and processing-job monitoring with
  workspace-scoped SQL read models and query-budget tests.
- Added a Windows hash-lock verification job alongside the Linux Python 3.11/3.12 clean installs.
- Migrated to the patched React Router package, removed the temporary advisory exception, and kept
  the dependency allowlist empty.

### Release checks

- Added one cross-platform command for dependency audits, Ruff, backend tests, complexity checks,
  frontend formatting and lint, unit tests, production build, fixture-browser tests, and one real
  full-stack browser journey.
- Added negative role tests for administrator APIs and authenticated shared invoice work.
- Added a React, FastAPI, SQLite, and worker browser journey covering upload, duplicate detection,
  correction, approval, and export.
- Added stale worker-lease recovery so interrupted jobs can be reclaimed without two workers
  processing the same active job.
- Added field-level source information and reviewer-correction history beside the PDF.
- Checked the six product pages for serious accessibility and overflow problems at every tested
  viewport.
- Regenerated and reviewed the screenshot matrix and 84-second captioned demo, including rendered
  PDF frames.
- Added a machine-readable release record containing the tested commit, counts, environment,
  durations, and reviewed dependency exceptions.

## Next validation work

Before processing real client data:

1. Run the documented usability study with 3–5 finance users. Record task failures and assistance
   without inventing results.
2. Validate 25 private invoices that can be used legally and remain outside Git.
3. Keep versioned labels and an experiment log for accuracy, latency, provider errors, and estimated
   cost.
4. Test messy scans, rotations, multiple pages, totals, currencies, duplicates, and missing values.
5. Review correction behavior and the failure taxonomy against those cases.
6. Complete the provider, retention, malware-scanning, and privacy checks listed in the security
   posture.
7. Publish a hosted demo or a one-command local demo after the seeded workflow is stable.

## Not planned yet

- a second document type;
- payment execution;
- chatbot or document Q&A;
- production multi-tenancy and billing;
- live ERP delivery without an approved integration;
- customer-impact, time-saving, or production-accuracy claims without observed data.
