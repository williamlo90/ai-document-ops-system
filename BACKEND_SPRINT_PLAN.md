# AI Document Operation System - Backend Sprint Plan

Status: Backend-specific execution plan. Use `blueprint.md` and `SPRINT_PLAN.md` as source-of-truth context.

Purpose: preserve the working invoice workflow while gradually introducing generic document-operation contracts and evaluation proof.

## Backend Strategy

Backend work should follow frontend identity cleanup, but it must not chase UI polish. It should add generic contracts only where they preserve or improve executable proof.

Correct order:

```text
baseline inventory
-> generic document workflow projection
-> document type taxonomy
-> generic evidence serialization
-> reviewer/work-item generalization
-> evaluation dataset pivot
-> optional credentials late
-> hardening
```

Invoice remains the first and only fully executable workflow until it is end-to-end strong.

## Backend Sprint 0 - API And Domain Inventory

### Goal

Map existing backend routes, services, repositories, models, tests, and fixtures before behavior changes.

### Work

- Inventory API routes for documents, invoices, backoffice, review, exports, integrations, providers, operations, AgentOps.
- Map feature-to-API relationships.
- Identify invoice-specific assumptions.
- Identify compatibility aliases needed before any route rename.
- Run baseline backend tests where practical.

### Likely Files

- `backend/app/main.py`
- `backend/app/api/`
- `backend/app/documents/`
- `backend/app/backoffice/`
- `backend/app/extraction/`
- `backend/app/validation/`
- `backend/app/agentops/`
- `backend/app/tests/`
- `docs/pivot/FEATURE_API_MATRIX.md`
- `docs/pivot/BASELINE_VERIFICATION.md`
- `docs/pivot/COMPATIBILITY_ALIASES.md`

### Verification

```powershell
python -m pytest backend/app/tests
```

Record pass/fail/skip honestly. Do not fix unrelated failures unless asked.

### Done

- Feature-to-API matrix exists.
- Backend compatibility risks are known.
- No behavior changes.

## Backend Sprint 1 - Generic Document Workflow Projection

### Goal

Expose a generic document workflow projection backed by existing invoice/work-item state.

### Work

- Add `DocumentWorkflowProjection` or equivalent typed structure.
- Add read endpoint such as `GET /documents/{document_id}/workflow`.
- Keep `GET /invoices/{document_id}/workflow` as compatibility alias.
- Ensure activity remains durable and audit-backed.
- Avoid new persistence unless necessary.

### Constraints

- No route removal.
- No second document type.
- No external credentials.
- No invented activity events.

### Tests

- Contract tests for generic projection.
- Regression test proving invoice endpoint and document endpoint match intended semantics.
- Service tests for projection adapter.

### Done

- A document workflow can be read without invoice-specific API shape.
- Invoice workflow remains backward compatible.

## Backend Sprint 2 - Document Type Taxonomy And Templates

### Goal

Introduce minimal document type support while keeping invoice as the only executable template.

### Work

- Add `DocumentType` contract.
- Add `OperationTemplate` contract if needed.
- Default existing documents to `invoice`.
- Add deterministic classifier hook that can return `invoice` or `unknown`.
- Ensure unknown type escalates/request classification instead of failing.
- Treat second type as stretch-only read-only preview.

### Constraints

- Invoice remains flagship executable workflow.
- No production ML classifier.
- No broad schema system.

### Tests

- Unit tests for taxonomy.
- Persistence/repository tests for document type.
- Planner tests for invoice and unknown fallback.

### Done

- Existing invoices are represented as `document_type=invoice`.
- Unknown types are safe.

## Backend Sprint 3 - Generic Evidence And Validation Contracts

### Goal

Separate generic evidence output from invoice-specific validation logic.

### Work

- Add generic evidence serializer:
  - field name;
  - normalized value;
  - confidence;
  - source page/text;
  - validation issues;
  - document type.
- Wrap invoice extraction into generic evidence output.
- Keep invoice validation adapter as first validator.
- Ensure missing evidence escalates.

### Constraints

- Do not rewrite extraction provider.
- Do not degrade invoice arithmetic validation.
- No real OCR/model requirement.

### Tests

- Validation tests for invoice adapter.
- Evidence serialization contract tests.
- Regression tests for existing extraction output.

### Done

- Backend can serve generic evidence while preserving invoice-specific validation.

## Backend Sprint 4 - Work Item And Reviewer Generalization

### Goal

Make work items and policy decisions document-operation aware without breaking existing invoice workflows.

### Work

- Generalize work types with compatibility mapping:
  - `invoice_review` -> `document_review`;
  - `vendor_follow_up` -> `evidence_follow_up`;
  - `invoice_export` -> `document_export`.
- Keep old values readable.
- Ensure policy decisions are type-aware.
- Ensure approval boundaries remain backend-enforced.

### Constraints

- No destructive migration.
- No unrestricted execution.
- No UI-only authorization.

### Tests

- Backoffice model/service tests.
- API tests for work item compatibility.
- Approval/policy tests.

### Done

- Reviewer workflow works with document-operation terminology at the backend contract level.

## Backend Sprint 5 - AgentOps Dataset Pivot

### Goal

Make reliability/evaluation data describe document operations.

### Work

- Add dataset fields for document type and operation type.
- Add scenarios:
  - invoice happy path;
  - missing evidence;
  - blocked execution;
  - low confidence;
  - provider failure;
  - approval required;
  - unknown document type.
- Preserve existing scenario history as compatibility evidence.

### Constraints

- No production model quality claim.
- Known failures must remain visible.

### Tests

- AgentOps service tests.
- Evaluation runner tests.
- Dataset validation tests.

### Done

- Evaluation runs against document-operation cases.
- Metrics remain traceable to underlying cases.

## Backend Sprint 6 - Integration Readiness Refresh

### Goal

Align provider/integration readiness with document operations while keeping mock/local default.

### Work

- Reframe OCR/extraction/storage/export integrations as document operation adapters.
- Ensure integration health is evidence-based.
- Ensure dashboards do not trigger paid provider calls.
- Update runtime/readiness docs from backend perspective.

### Constraints

- No real provider setup by default.
- No production deployment claim.

### Tests

- Integration status tests.
- Provider health tests.
- Settings tests.

### Done

- Runtime/provider status is truthful and local-first.

## Backend Sprint 7 - Optional External Credentials

### Goal

Add optional credential path without making it required.

### Work

- Verify `.env.example`.
- Document optional Supabase/Postgres, object storage, OCR/LLM, email/accounting integrations.
- Ensure local startup works without `.env`.
- Ensure production-like mode rejects unsafe partial credentials.

### Constraints

- No mandatory external services.
- No required paid calls.

### Tests

- Settings tests.
- Provider factory tests.
- Local startup smoke.
- Optional profile smoke only if credentials are intentionally supplied.

### Done

- Real credentials are optional and late.
- Mock mode remains default.

## Backend Sprint 8 - Hardening And Release Evidence

### Goal

Prepare backend proof for portfolio review.

### Work

- Confirm health/readiness truthfulness.
- Confirm security headers/rate limiting/session behavior.
- Confirm export/provider actions remain bounded.
- Update runbook and release notes.
- Capture verification summary.

### Tests

- Backend suite.
- Smoke scripts where available.
- Demo workflow smoke.

### Done

- Backend supports the flagship workflow with honest evidence and no unsupported production claims.

## Backend Execution Rule

Run one backend sprint at a time. Do not remove old invoice contracts until replacement contracts pass tests.

