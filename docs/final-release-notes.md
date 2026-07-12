# Release Notes - AI Document Operations System

Status: local-first Project 4 document-operations release candidate.

Completed:

- Project 4 was built from the Project 3.5 AgentOps reliability baseline.
- Document intake, storage, processing jobs, Work Queue, audit activity, and workflow evidence remain intact.
- Back-office work items, bounded planning, policy checks, drafts, approvals, and controlled execution are implemented.
- AgentOps APIs support reliability summaries, run traces, planning-version evidence, regression comparison, and scenario evaluation.
- Project 4 back-office scenarios are versioned and evaluated with document type and operation type dimensions.
- Scenario evaluation results persist expected and actual document/operation evidence for refresh and SQLite restart cases.
- React operator UI exposes Work Queue, Review, Approval Decision, Record, Safety Rules, History, Technical Evidence, System Reliability, Reliability Checks, Test Scenarios, and Run Traces.
- Docker, CI, public artifact packaging, integration setup guidance, and portfolio demo docs are included.

Verification:

- Frontend tests and production build passed after the UX simplification and demo-language alignment pass.
- Backend AgentOps API and SQLite persistence tests passed for persisted document-operation evidence.
- Full backend suite passed: 356 tests OK, 2 skipped.
- Public artifact tests passed: 16 tests OK.

Known limitations:

- Invoice is still the only complete extraction, validation, planning, and execution schema.
- Generic `/documents/*` contracts are additive; invoice compatibility aliases remain intentionally supported.
- A second executable document workflow is deferred until extraction, validation, planning, execution, and evaluation contracts are covered.
- This is a local-first portfolio system, not hosted production SaaS.
- Real customer deployment, tenancy, billing, backups, production monitoring, and live-provider credentials are out of scope for this release.
- Token and real cost tracking require a future LLM planner.
