# Keep, Refactor, Remove, Rebuild Inventory

Status: Main Sprint 0 decision record, 2026-07-08.

## Keep

- FastAPI composition, security/session boundaries, workspace isolation, and HTTP security controls.
- Document upload, storage, PDF serving, jobs, retries, and durable operational events.
- Work item, plan, policy, draft, approval, bounded execution, and audit spine.
- SQLite local-first repositories and optional provider/integration boundaries.
- Invoice extraction and arithmetic validation as the first schema adapter.
- AgentOps run persistence, scenario evaluation, regression evidence, and known-failure reporting.
- React/Vite operator console and the completed Frontend Sprints 0-6.

## Refactor Additively

- Add a generic document workflow projection beside `/invoices/{id}/workflow`.
- Add `document_type`, operation taxonomy, and operation templates with invoice defaults.
- Wrap invoice extraction in a generic evidence contract.
- Generalize work-type and recovery-command vocabulary through adapters/mappers.
- Extend AgentOps datasets with document type and operation type dimensions.
- Rename backend product metadata from `Doc Intel MVP` after a metadata test is updated.

## Hide Or Remove Later

- Broad autonomous claims and unsupported generic controls; frontend wording is already corrected.
- Duplicate legacy UI routes after generic routes are proven and documented.
- Invoice-only names from shared serializers only after compatibility consumers migrate.

No current behavior or endpoint is approved for immediate deletion.

## Rebuild

Nothing. The existing architecture has a reusable operational spine. New generic contracts should be adapters and additive domain concepts, not a rewrite.

## Deferred

- A second executable document workflow.
- Production ML classification.
- Required cloud/Supabase/OCR/LLM credentials.
- Destructive database or route migration.

