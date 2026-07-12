# Architecture - AI Document Operations System

The system extends a document platform and reliability engine into bounded document-operation workflows.

## High-Level Flow

```text
work item intake
-> classify work type
-> extract or attach business context
-> create action plan
-> apply execution policy
-> draft safe next actions
-> request human approval when needed
-> execute confirmed tools
-> record audit trail
-> record AgentOps run
-> evaluate reliability
-> operator dashboard
```

## Role-Aware Presentation Architecture

The core domain remains generic. Guided user interfaces consume a workflow projection rather than encoding business state independently.

```text
documents + extraction + validation
              |
work item + plan + approval + execution
              |
audit events + AgentOps evidence
              v
document workflow projection (invoice implementation today)
              |
intake operator UI / administrator-reviewer UI
```

The projection should expose:

- current stage
- current owner
- waiting-for reason
- next permitted action
- attention reason
- completed workflow stages
- durable activity events

Invoice-specific labels belong in type-specific evidence components. Generic work-item, policy, approval, tool, and technical-evidence models remain reusable for future document workflow modules.

Progress UI must be backed by durable state or events. The frontend must not simulate successful processing stages with timers.

## Workflow Aggregate

`GET /invoices/{document_id}/workflow` is the read model for invoice status and Activity. It combines:

- durable document audit events
- durable backoffice workflow events
- extraction and validation evidence
- the current work item, plan, approvals, and execution state
- derived stage, owner, waiting-for reason, next action, and attention reason

The React Activity tab polls this aggregate every five seconds. Recovery commands are explicit:

- `POST /invoices/{document_id}/retry`
- `POST /invoices/{document_id}/request-correction`
- `POST /invoices/{document_id}/escalate`

AgentOps run linkage remains a separate Phase 5 responsibility; the aggregate does not fabricate trace identifiers.

## Source System

Project 4 inherits:

- document upload, parsing, extraction, validation, review, and export workflow
- controlled copilot tools
- tool contracts and risk levels
- confirmation-required execution
- human escalation
- failure taxonomy
- agent run records and tool traces
- AgentOps evaluation, scenario datasets, prompt comparison, and regression comparison

## Operational Modules

- `app.backoffice.models`: work items, task plans, action drafts, approvals, and policy decisions
- `app.backoffice.policy`: autonomy levels, risk classification, and execution gates
- `app.backoffice.planner`: deterministic planning over known workflow state
- `app.backoffice.service`: orchestration service for intake, planning, drafting, and controlled execution
- `app.api.backoffice`: JSON endpoints for work items, plans, approvals, and execution
- `app.ui` extension: operator inbox, work item detail, plan review, and action confirmation views
- `app.agentops` extension: document-operation run metrics and scenario evaluation
- `backend/app/tests/test_backoffice*.py`: model, policy, service, API, UI, and boundary tests

## Core Domain Objects

Work item:

- id
- workspace id
- source type
- work type
- priority
- status
- linked document ids
- extracted business context
- current plan id

Task plan:

- id
- work item id
- planner version
- steps
- overall confidence
- escalation reason

Action step:

- action id
- action type
- tool name
- risk level
- required approval
- status
- why this action
- why not alternatives

Action draft:

- id
- work item id
- draft type
- safe preview content
- approval status
- execution result

Policy decision:

- action type
- autonomy level
- allowed or blocked
- confirmation requirement
- reason

## Autonomy Levels

- `read_only`: inspect state, summarize, and explain
- `recommend`: propose next action without mutation
- `draft`: prepare message, note, or export preview without external side effects
- `confirm_execute`: execute only after explicit human confirmation
- `blocked`: refuse unsafe, unsupported, cross-workspace, or high-risk action

## Guardrail Principle

Autonomy is not a binary switch.

Project 4 should treat autonomy as a policy-controlled workflow:

```text
Can inspect freely.
Can recommend carefully.
Can draft safely.
Can execute only when allowed and confirmed.
Must escalate when uncertain.
Must refuse when unsafe.
```

## AgentOps Integration

Every AI-assisted document workflow should remain measurable:

- selected work type
- planned actions
- executed tools
- blocked actions
- human escalations
- confidence
- failure type
- prompt or planner version
- scenario dataset version
- estimated cost

User-facing AI explanations may use stored confidence, validation results, policy reasons, and safe tool-selection reasons. They must not expose private chain-of-thought or invent evidence that the system did not record.

## Intake Operator Boundary

The intake experience is document-first. Operators upload and verify invoices without
needing to understand internal work-item records.

- `DocumentRecord` persists `submitted_by` and `size_bytes`.
- `GET /documents/upload-policy` exposes the accepted limit and duplicate candidates.
- `GET /documents/{id}/content` streams a workspace-scoped PDF preview.
- `POST /invoices/{id}/draft` persists corrected header fields and line items, then
  reruns deterministic invoice validation.
- `GET /invoices` provides workspace-scoped search, status/date filtering, submitter
  filtering, and server pagination.
- Intake cancellation moves the document and queued job to explicit `cancelled`
  states. Reprocessing creates a new queued job from an allowed recovery state.
- PDF download reuses the authenticated, workspace-scoped content endpoint.
- Submission creates one linked work item and plan through idempotency keys. It does
  not grant the intake operator reviewer approval authority.

## Reviewer Operations Boundary

Reviewer-facing work-item metadata remains part of the durable aggregate. Title and
priority are domain fields; assignee, requested outcome, and tags use the existing
business context until a dedicated identity service is introduced.

- `PATCH /backoffice/work-items/{id}` records ownership and metadata changes.
- Draft editing updates an active draft; regeneration creates a separate version.
- Work-item detail includes durable workflow activity for decision and execution evidence.
- Queue selection and bulk priority changes use the same workspace-scoped update API.
- The reviewer UI follows Understand, Review Plan, Decide, and Confirm Result stages.

Provider health is evidence-based rather than a blind connectivity claim:

- mock providers report healthy when their deterministic runtime is available;
- configured external providers report `ready_unverified` until a real run is observed;
- observed provider failures move health to `degraded`;
- opening the dashboard never creates a paid provider request.

The Attention Inbox projects exception-specific views from work type, work-item state,
linked document validation state, and approval state. These are queue projections, not
separate copies of the underlying work item.

## Deployment Direction

Project 4 remains local-first at setup time.

The architecture should remain compatible with:

- Docker Compose for local services
- CI quality gates
- future Postgres-backed persistence
- future object storage
- future cloud deployment
- future Kubernetes/AWS portfolio extension

Deployment work should not weaken autonomy guardrails.
