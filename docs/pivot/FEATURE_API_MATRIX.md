# Feature-to-API Matrix

Status: Main Sprint 0 inventory, 2026-07-08.

| Product capability | Current UI | Current API / module | Pivot decision | Next contract |
|---|---|---|---|---|
| Secure operator session | Login/session verification | `/auth/session` | Keep | No rename |
| Document intake | New Document wizard | `/documents/upload-policy`, `/documents/upload`, `/documents/{id}/process` | Keep | Add `document_type` later |
| Document library | My Documents, Document Library | `GET /documents`, `GET /invoices` | Refactor | Generic list owns common fields; invoice list remains alias |
| Source preview | Workspace PDF preview | `/documents/{id}/content`, `/documents/{id}/download-url` | Keep | No domain rename |
| Extraction evidence | Workspace evidence panels | `GET /documents/{id}`; `extraction/schemas.py` | Refactor | Generic evidence serializer plus invoice adapter |
| Validation | Validation findings and line-item checks | `validation/invoice.py`, review APIs | Refactor | Validator selected by document type |
| Document queue | Operations queue and exceptions | `/backoffice/workspace`, `/backoffice/work-items/*` | Refactor | Generic operation vocabulary with compatibility mapping |
| Workflow projection | Workspace Activity | `GET /invoices/{id}/workflow`; `backoffice/workflow_projection.py` | Refactor | Add `GET /documents/{id}/workflow` |
| Planning and policy | Plan and Governance tabs | `/backoffice/work-items/{id}/plan`; planner/policy modules | Refactor | Operation template drives plan; policy remains backend authority |
| Human approval | Approval inbox/detail | `/backoffice/approvals/{id}/approve|reject` | Keep | Do not add unsupported approval states |
| Correction/escalation | Activity recovery commands | `/invoices/{id}/request-correction|escalate` | Refactor | Generic document-operation commands with invoice aliases |
| Controlled execution | Approved plan-step execution | `/backoffice/work-items/{id}/steps/{step_id}/execute` | Keep | Type-aware tool policy |
| Export | Export action and CSV/JSON artifacts | `/exports/*`, `/integrations/accounting/documents/{id}/export` | Refactor | Generic document export contract; retain invoice CSV |
| Durable activity/audit | Activity and Operational Controls | workflow projection, `/operations/audit.csv`, jobs APIs | Keep | Generic event vocabulary, no invented events |
| Reliability evidence | Technical Evidence pages | `/agentops/*`, benchmark/evaluation modules | Refactor | Slice by document and operation type |
| Provider/runtime status | System health, Integrations, Settings | `/providers/health`, `/integrations/status`, `/operations/jobs` | Keep | Evidence-based status labels only |

## Current Boundary

- Invoice is the only complete extraction, validation, planning, and execution schema.
- Document upload/storage and much of the work-item/audit spine are already reusable.
- The missing generic seam is the workflow/evidence contract, not a replacement application.
- The frontend may use document-first language, but backend aliases remain invoice-specific until covered by generic contract tests.

