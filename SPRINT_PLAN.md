# AI Document Operation System - Sprint Plan

Status: Planning source for implementation. Use `blueprint.md` as the source of truth.

## 1. Baseline Summary

### Frontend

- React/Vite single-page operator console.
- Role-aware shell for intake operator and administrator/reviewer.
- Existing invoice intake wizard, submissions/library views, reviewer inbox, work item detail, plan, drafts, approvals, activity, operations, integrations, settings, reliability, evaluation, and datasets.
- Current UI is rich but still invoice/backoffice-labeled in many user-facing paths.

### Backend

- FastAPI modular application with document, invoice, backoffice, review, exports, integrations, metrics, providers, operations, agent, and AgentOps APIs.
- Document upload, PDF content serving, processing jobs, extraction, validation, correction, retry, escalation, approval, export, and workflow projection.
- SQLite local-first repositories with production-shaped PostgreSQL migration tooling.
- Provider boundaries for mock/OCR/extraction/storage/integration health.

### Architecture

- Strong reusable spine: document intake -> extraction -> validation -> work item -> plan -> policy decision -> draft -> approval -> execution -> audit -> AgentOps.
- Durable workflow events and idempotent commands already exist for much of the invoice path.
- The architecture should be generalized, not replaced.

### Proof Assets

- Broad backend tests across API, services, validation, persistence, security, workflow, backoffice, benchmarks, AgentOps, integrations, and operations.
- Frontend unit/E2E tests.
- Evaluation datasets, AgentOps scenarios, benchmark reports, runbooks, deployment docs, object storage docs, backup/restore docs, UI plans, and readiness docs.

## 2. Smallest Safe Pivot Path

The safest path is an incremental compatibility migration:

```text
keep invoice workflow working
-> rename product and user-facing labels
-> introduce generic document operation vocabulary beside invoice vocabulary
-> generalize workflow projection and data contracts
-> add one non-invoice document type
-> expand evaluation and AgentOps by document type
-> migrate route/API names only after behavior is covered by tests
```

Invoice remains the first supported document type. Existing invoice endpoints may stay as compatibility aliases until generic document operation endpoints are proven.

## 3. Migration Strategy

- Use additive domain concepts first: `document_type`, `operation_type`, `document_operation`, and `operation_template`.
- Keep current invoice tables/models/routes until generic equivalents pass tests.
- Introduce serializers/adapters that map invoice workflow state into generic document operation projections.
- Update UI copy before changing persistence shape.
- Rename routes late, and keep redirects or aliases where useful.
- Preserve every working test as regression coverage. Add generic tests before deleting invoice-specific assumptions.
- Never remove an invoice feature until the generic document operation path has equivalent behavior and verification.

## 3.1 Local-First And Credential-Late Strategy

The sprint plan is local-first by default.

Early and middle sprints must not require real Supabase, cloud, OCR, LLM, email, accounting, object-storage, hosted deployment, or CI secrets. They may define interfaces, adapters, config schemas, and `.env.example`, but the application must remain runnable in local/mock mode without paid external services.

Default development mode:

- local SQLite or existing local persistence path;
- local/mock storage;
- deterministic/mock extraction provider;
- fake accounting/export adapter;
- seeded invoice/vendor fixtures;
- replayable evaluation datasets;
- no real external provider calls during ordinary UI navigation.

Real external providers are deferred to late sprints:

- managed Supabase/Postgres;
- object storage;
- OCR/LLM provider keys;
- email/vendor/accounting integrations;
- hosted deployment credentials;
- CI secrets.

Principle:

> Design provider boundaries early. Require real credentials late.

## 4. Sprint Sequence

## Sprint 0 - Pivot Contract And Inventory

### Goal

Freeze the pivot boundary and produce an actionable map from invoice/backoffice surfaces to generic document operations.

### Scope

- Inventory every route, page, API, domain model, fixture, and test that contains invoice/backoffice-specific language.
- Classify each item as keep, refactor, hide/remove, or rebuild.
- Produce a feature-to-API matrix for the new product.

### Likely Files

- `blueprint.md`
- `SPRINT_PLAN.md`
- `README.md`
- `ARCHITECTURE.md`
- `docs/`
- `frontend/src/App.tsx`
- `backend/app/api/`
- `backend/app/backoffice/`
- `backend/app/documents/`
- `backend/app/tests/`

### Backend Work

- No behavior change.
- Document current generic-vs-invoice domain boundaries.
- Identify compatibility aliases required for future sprints.

### Frontend Work

- No UI behavior change.
- Inventory visible labels, page groups, role flows, and controls.

### Data/Model Changes

- None.

### Tests And Verification

- Run existing backend and frontend checks if environment is ready.
- Capture current failing/passing status as baseline.
- Verify no source repository files were modified.

### Acceptance Criteria

- Feature-to-API matrix exists.
- Every visible invoice/backoffice surface has a pivot decision.
- First implementation sprint can begin without guessing scope.

### Non-Goals

- No code migration.
- No database migration.
- No route rename.

## Sprint 1 - Product Identity And UI Language

### Goal

Make the copied repository present as AI Document Operation System while preserving existing behavior.

### Scope

- Rename product copy, README, page titles, sidebar labels, role labels, empty states, notices, and footer claims.
- Change invoice-only operator labels to document-first labels where behavior is already generic enough.
- Keep invoice-specific fields visible only inside invoice evidence/detail sections.

### Likely Files

- `README.md`
- `PRD.md`
- `ARCHITECTURE.md`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/src/test/App.test.tsx`
- `frontend/e2e/*.spec.ts`

### Backend Work

- Update FastAPI title and safe product metadata only if tests cover it.
- Keep `/invoices` APIs untouched.

### Frontend Work

- Rename:
  - New Invoice -> New Document
  - My Submissions -> My Documents
  - All Invoices -> Document Library
  - Invoice Intake -> Document Intake
  - Invoice Review -> Document Review
- Add explicit "Invoice" type badge for the current workflow.
- Remove unsupported generic claims from UI.

### Data/Model Changes

- None.

### Tests And Verification

- Frontend unit tests.
- Playwright smoke for login, document upload path, library, reviewer inbox, work item detail.
- Backend smoke only if API metadata changed.

### Acceptance Criteria

- Default UI identity is AI Document Operation System.
- Existing invoice happy path still works.
- No enabled control claims generic document behavior that is not implemented.

### Non-Goals

- No generic document schema yet.
- No endpoint rename.
- No non-invoice upload support claim.

## Sprint 2 - Document Operation Projection

### Goal

Introduce a generic document workflow projection while preserving the invoice workflow as the first implementation.

### Scope

- Add generic projection contracts for document operation status, owner, waiting reason, next action, evidence summary, plan, approvals, and activity.
- Implement projection adapter backed by existing invoice/work-item state.

### Likely Files

- `backend/app/documents/`
- `backend/app/backoffice/workflow_projection.py`
- `backend/app/api/documents.py`
- `backend/app/api/invoices.py`
- `backend/app/api/serializers.py`
- `backend/app/tests/test_*workflow*.py`
- `frontend/src/App.tsx`

### Backend Work

- Add `DocumentWorkflowProjection` or equivalent typed structure.
- Add read endpoint such as `GET /documents/{document_id}/workflow`.
- Keep `GET /invoices/{document_id}/workflow` as compatibility alias.
- Ensure activity remains durable and audit-backed.

### Frontend Work

- Read generic workflow projection for document status screens where possible.
- Keep invoice-specific rendering isolated in type-specific evidence components.

### Data/Model Changes

- Add no new persistence unless current state cannot represent document type.
- If needed, add nullable/default `document_type='invoice'` through migration/repository adapter.

### Tests And Verification

- Contract tests for generic projection.
- Regression tests proving invoice workflow endpoint matches generic projection semantics.
- Frontend tests for document status/activity rendering.

### Acceptance Criteria

- A document workflow can be read without using invoice terminology in the API response shape.
- Invoice workflow remains backward compatible.
- Activity contains no invented events.

### Non-Goals

- No second document type yet.
- No extraction schema rewrite.

## Sprint 3 - Document Type Taxonomy And Operation Templates

### Goal

Add the minimal domain layer needed to support multiple document operation types.

### Scope

- Introduce document type taxonomy and operation templates.
- Keep `invoice` as the only fully executable template.
- Treat any second document type as a stretch-only read-only preview. Do not implement it unless the invoice workflow remains fully passing and the sprint budget has room.

### Likely Files

- `backend/app/documents/models.py`
- `backend/app/documents/services.py`
- `backend/app/documents/sqlite_repositories.py`
- `backend/app/backoffice/models.py`
- `backend/app/backoffice/planner.py`
- `backend/app/tests/test_documents*.py`
- `backend/app/tests/test_backoffice*.py`

### Backend Work

- Add `DocumentType` and `OperationTemplate` contracts.
- Classify existing uploads as `invoice` by default.
- Add deterministic classifier hook that can return `unknown` or configured type.
- Ensure planner uses operation template rather than hardcoded invoice-only names.

### Frontend Work

- Show document type badges.
- Add document type filter in library if backend supports it.
- Keep non-invoice template clearly labelled as preview/read-only until full workflow exists.

### Data/Model Changes

- Migration/repository update for `document_type`.
- Seed/demo data update.

### Tests And Verification

- Unit tests for taxonomy and classifier fallback.
- Persistence tests for document type.
- Planner tests for invoice template and unknown-type escalation.

### Acceptance Criteria

- Existing invoices are represented as `document_type=invoice`.
- Unknown document types do not break workflow; they escalate or request classification.
- No non-invoice document is presented as fully automated.
- The invoice workflow remains the only flagship executable workflow.

### Non-Goals

- No generic extraction provider rewrite.
- No production ML classifier.
- No required second document type implementation.

## Sprint 4 - Generic Evidence And Validation Layer

### Goal

Separate generic document evidence from invoice-specific extraction fields.

### Scope

- Introduce evidence field model with field name, normalized value, confidence, source page/text, validation issues, and document type.
- Keep invoice validation adapter as the first schema-specific validator.
- Add minimal second schema fixture for one non-invoice type.

### Likely Files

- `backend/app/extraction/`
- `backend/app/validation/`
- `backend/app/documents/`
- `backend/app/api/serializers.py`
- `backend/app/tests/test_validation.py`
- `examples/evaluation/`
- `frontend/src/App.tsx`

### Backend Work

- Add generic evidence serializer.
- Wrap invoice extraction into generic evidence output.
- Route validation through document-type-specific adapters.

### Frontend Work

- Build or refactor evidence panel to render generic fields.
- Preserve invoice line-item/arithmetic panels only for invoice type.

### Data/Model Changes

- Add evidence contract; persistence may remain derived from extraction if durable enough.

### Tests And Verification

- Validation tests for invoice adapter.
- Evidence serialization contract tests.
- Frontend tests for generic evidence panel and invoice-specific detail.

### Acceptance Criteria

- UI can render evidence without hardcoding invoice field names.
- Invoice arithmetic/validation behavior remains intact.
- Missing evidence escalates rather than fabricating values.

### Non-Goals

- No broad OCR quality improvement.
- No real-provider benchmark unless credentials are configured.

## Sprint 5 - Reviewer Workspace Generalization

### Goal

Make the reviewer workspace operate on document operations rather than invoice exceptions.

### Scope

- Refactor work item copy, filters, tabs, and action labels around document operation status.
- Keep plan, draft, approval, execution, activity, and AgentOps tabs.
- Ensure every visible control maps to a real backend command or is disabled with a truthful reason.

### Likely Files

- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `backend/app/api/backoffice.py`
- `backend/app/backoffice/services.py`
- `backend/app/backoffice/policy.py`
- `backend/app/tests/test_backoffice*.py`
- `frontend/e2e/workflow.spec.ts`

### Backend Work

- Generalize work types:
  - `invoice_review` -> `document_review`
  - `vendor_follow_up` -> `evidence_follow_up`
  - `invoice_export` -> `document_export`
- Keep compatibility mapping for existing data.
- Ensure policy decisions are type-aware.

### Frontend Work

- Update inbox filters and detail pages.
- Use document evidence instead of invoice-only summary in reviewer flow.
- Update copy for approve/reject/escalate/request correction.

### Data/Model Changes

- Optional migration or mapper for old work type values.

### Tests And Verification

- Backoffice service and API tests.
- Frontend E2E for reviewer exception resolution.
- Accessibility smoke for reviewer flow.

### Acceptance Criteria

- Reviewer can resolve an invoice document operation through generalized UI.
- Work item detail no longer depends on invoice-only labels except inside invoice evidence.
- Approval boundaries remain enforced by backend.

### Non-Goals

- No new external integrations.
- No unrestricted execution.

## Sprint 6 - AgentOps Dataset Pivot

### Goal

Make AgentOps reliability evidence describe document operations rather than autonomous backoffice only.

### Scope

- Add document-operation scenario dataset.
- Preserve existing scenario history as compatibility evidence.
- Report outcomes by document type, operation type, risk, missing evidence, approval, execution, and failure type.

### Likely Files

- `backend/app/agentops/`
- `backend/app/benchmark/`
- `examples/agentops/`
- `examples/evaluation/`
- `backend/app/tests/test_agentops*.py`
- `frontend/src/App.tsx`

### Backend Work

- Add dataset schema fields for document type and operation type.
- Add scenarios for invoice happy path, missing evidence, blocked execution, low confidence, provider failure, approval required, and unknown document type.

### Frontend Work

- Update Reliability, Evaluation, and Datasets labels.
- Show document-operation slices without hiding failures.

### Data/Model Changes

- New dataset fixtures.
- No destructive history migration.

### Tests And Verification

- AgentOps service tests.
- Evaluation runner tests.
- Frontend tests for reliability/evaluation display.

### Acceptance Criteria

- Evaluation can run against document-operation cases.
- Metrics link to underlying cases.
- Known failures remain visible.

### Non-Goals

- No model quality claim from local mock data.
- No production SLO.

## Sprint 7 - Integration And Runtime Readiness Refresh

### Goal

Align integrations, runtime docs, and readiness claims with the new product scope.

### Scope

- Reframe OCR/extraction/storage/export integrations as document operation adapters.
- Keep sandbox/mock mode first.
- Update runbooks and readiness docs to AI Document Operation System.

### Likely Files

- `INTEGRATION_SETUP_GUIDE.md`
- `DEPLOYMENT_READINESS.md`
- `RUNBOOK.md`
- `BACKUP_AND_RESTORE.md`
- `docs/`
- `backend/app/api/integrations.py`
- `backend/app/integrations/`
- `backend/app/providers/`

### Backend Work

- Ensure integration health is evidence-based.
- Confirm no dashboard opening triggers paid provider calls.

### Frontend Work

- Update Settings, Integrations, System Health, and runtime/provider indicator labels.

### Data/Model Changes

- None unless integration names are persisted.

### Tests And Verification

- Integration status tests.
- Provider health tests.
- Documentation command smoke where practical.

### Acceptance Criteria

- Runtime docs match actual commands.
- Integration cards do not imply unverified connectivity.
- Local deterministic mode remains the default demo path.

### Non-Goals

- No real provider setup by default.
- No production deployment claim.

## Sprint 8 - Optional External Integration And Credential Setup

### Goal

Add a documented optional path for real credentials without making them required for the portfolio demo.

### Scope

- Verify or create `.env.example`.
- Document optional Supabase/Postgres setup.
- Document optional object storage setup.
- Document optional OCR/LLM provider setup.
- Document optional email/vendor/accounting integration setup.
- Add startup/config behavior that fails safely when optional credentials are absent.
- Keep local/mock mode as the default.

### Likely Files

- `.env.example`
- `INTEGRATION_SETUP_GUIDE.md`
- `DEPLOYMENT_READINESS.md`
- `RUNBOOK.md`
- `backend/app/core/settings.py`
- `backend/app/providers/`
- `backend/app/integrations/`
- `backend/app/tests/test_settings.py`
- `backend/app/tests/test_provider_factory.py`
- `backend/app/tests/test_integrations.py`

### Backend Work

- Ensure optional providers are opt-in.
- Ensure missing optional credentials do not break local startup.
- Ensure production-like mode rejects unsafe partial credentials.
- Confirm dashboards do not trigger paid provider calls.

### Frontend Work

- Make integration/provider status labels explicit:
  - `mock`
  - `configured_unverified`
  - `ready_verified`
  - `degraded`
  - `not_configured`

### Data/Model Changes

- None unless provider profile metadata is persisted.

### Tests And Verification

- Settings tests for missing optional credentials.
- Provider factory tests for mock default.
- Integration status tests.
- Local startup without `.env`.
- Optional profile smoke only if credentials are intentionally supplied.

### Acceptance Criteria

- The app runs locally without real credentials.
- `.env.example` documents optional integrations clearly.
- Real credentials are not required for portfolio evaluation.
- Production-like mode does not silently pretend optional providers are healthy.

### Non-Goals

- No mandatory Supabase migration.
- No mandatory paid OCR/LLM call.
- No production SaaS deployment.

## Sprint 9 - Production-Like Hardening And Portfolio Packaging

### Goal

Prepare the project for public portfolio review without overstating production readiness.

### Scope

- CI or documented local quality gates.
- Smoke test path for local/mock mode.
- Security/readiness review.
- Backup/restore notes if persistence path supports it.
- Demo script.
- Screenshots.
- Short case study.
- Known limitations.

### Likely Files

- `README.md`
- `PORTFOLIO_STORY.md`
- `docs/demo-script.md`
- `docs/final-release-notes.md`
- `DEPLOYMENT_READINESS.md`
- `RUNBOOK.md`
- `PROJECT_4_READINESS.md` or renamed equivalent
- `scripts/`

### Backend Work

- Confirm health/readiness status is truthful.
- Confirm security headers/rate limiting/session behavior still pass tests.
- Confirm export and provider actions remain bounded.

### Frontend Work

- Capture current workflow screenshots.
- Ensure first screen clearly communicates document operations.
- Ensure Technical Evidence points to real tests/evaluation assets.

### Data/Model Changes

- None.

### Tests And Verification

- Backend test suite.
- Frontend unit tests.
- Playwright smoke where available.
- Local app start.
- Demo workflow smoke.

### Acceptance Criteria

- A recruiter can understand the product in 60 seconds.
- A hiring manager can inspect workflow/evaluation proof in 10 minutes.
- The README says exactly what is implemented and what is not.
- No production, real-customer, or real-provider claim is unsupported.

### Non-Goals

- No new product features.
- No broad second workflow.
- No paid external service requirement.

## 5. Risk Controls

- AI workflow: models only classify, extract, summarize, plan, draft, and support evaluation; deterministic code gates execution.
- Approval: risky or low-confidence actions require backend-enforced approval.
- Audit: every state change and command writes durable activity/audit evidence.
- AgentOps: every AI claim links to runs, scenarios, versions, or evaluation cases.
- Migration: keep invoice aliases until generic paths pass regression tests.
- UI truthfulness: no fake progress, fake trace IDs, static health, or decorative enabled controls.

## 6. Recommended First Sprint

Start with **Sprint 0 - Pivot Contract And Inventory**.

Why: the repository is already large and feature-rich. The main risk is accidental broad rewrite or breaking working invoice proof while renaming the product. Sprint 0 creates the control map needed to move quickly without losing evidence.

Evidence required before Sprint 1:

- Feature-to-API matrix.
- Keep/refactor/remove/rebuild inventory.
- Baseline test status.
- Confirmed list of compatibility aliases.

## 7. Sprint 0 Execution Checklist

Execute Sprint 0 before any product behavior changes.

### Order Of Operations

1. Re-read `blueprint.md` and this `SPRINT_PLAN.md`.
2. Confirm the working directory is the Agentic Project copy, not the old learning repository.
3. Inventory frontend user-facing labels and route/page groups.
4. Inventory backend API routes and domain modules.
5. Inventory tests that encode invoice/backoffice terminology.
6. Create the feature-to-API matrix.
7. Create the keep/refactor/remove/rebuild inventory.
8. Run baseline verification commands that are practical in the local environment.
9. Record current pass/fail/skip status without fixing unrelated failures.
10. Stop. Do not start Sprint 1 in the same pass unless explicitly asked.

### Suggested Commands

Use the available package managers and existing scripts. If a command fails due to missing dependencies, record that as baseline evidence.

```powershell
cd "C:\Users\William\OneDrive\Dokumen\Agentic Project\ai-document-ops-system"
python -m pytest backend/app/tests
cd frontend
npm test
npm run build
npx playwright test
```

If the repository uses helper scripts instead, prefer the existing project commands documented in `README.md` or `RUNBOOK.md`.

### Likely Sprint 0 Output Files

- `docs/pivot/FEATURE_API_MATRIX.md`
- `docs/pivot/KEEP_REFACTOR_REMOVE_REBUILD.md`
- `docs/pivot/BASELINE_VERIFICATION.md`
- `docs/pivot/COMPATIBILITY_ALIASES.md`

### Files To Inspect Before Editing

- `README.md`
- `PRD.md`
- `ARCHITECTURE.md`
- `frontend/src/App.tsx`
- `backend/app/main.py`
- `backend/app/api/`
- `backend/app/documents/`
- `backend/app/backoffice/`
- `backend/app/tests/`

## 8. Credential And Environment Strategy

### Default Profile

The default profile is local/mock. It must run without real credentials.

### `.env.example`

`.env.example` should document optional settings, not imply they are required for development. Required local settings should have safe defaults whenever possible.

### Deferred Credentials

Do not require these until Sprint 8 or later:

- Supabase/Postgres managed database;
- cloud object storage;
- OCR provider keys;
- LLM provider keys;
- email provider keys;
- accounting/export integration credentials;
- hosted deployment secrets;
- CI secrets.

### Safe Failure Behavior

If optional credentials are absent:

- local app startup should still work;
- mock providers should be selected;
- integration status should report `not_configured` or `ready_unverified`;
- dashboards must not claim verified health;
- no UI action should trigger paid provider calls without explicit provider configuration.

## 9. Portfolio Success Criteria

### Recruiter: 60 Seconds

The first screen and README must make this clear:

- The product is an AI Document Operations System.
- It solves invoice/vendor document workflow pain.
- It is not a chatbot.
- It has a live/local demo path.
- It has screenshots or a demo script.

### Hiring Manager: 10 Minutes

The repository must prove:

- document intake works;
- extraction and validation are structured;
- exceptions route to review;
- approvals and risky actions are controlled;
- exports/actions are bounded;
- audit/activity evidence exists;
- evaluation and AgentOps evidence exist;
- limitations are explicit.

### Technical Proof

Required proof before calling this flagship-ready:

- end-to-end invoice/vendor workflow;
- backend tests for workflow, validation, approval, and export boundaries;
- frontend tests or E2E smoke for intake/review path;
- evaluation dataset with passing and known-failing cases;
- local runbook;
- no real credential requirement;
- clear portfolio case study.
