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

- Full backend suite passed: 356 tests OK, 2 skipped.
- Frontend tests passed: 8 tests OK.
- Frontend lint passed.
- Frontend production build passed.
- Docker compose config check passed.
- Public artifact packaging script passed to a temporary output folder.
- Backend AgentOps API and SQLite persistence coverage remains green inside the full backend suite.
- Black and Ruff were not rerun in the final audit because the current local `.venv` does not include those modules; earlier backend/product sprints had run them successfully.

Known limitations:

- Invoice is still the only complete extraction, validation, planning, and execution schema.
- Generic `/documents/*` contracts are additive; invoice compatibility aliases remain intentionally supported.
- A second executable document workflow is deferred until extraction, validation, planning, execution, and evaluation contracts are covered.
- This is a local-first portfolio system, not hosted production SaaS.
- Real customer deployment, tenancy, billing, backups, production monitoring, and live-provider credentials are out of scope for this release.
- Token and real cost tracking require a future LLM planner.

Release verdict:

This release is demo-ready as a local-first, invoice-first AI Document Operations System. It is not a hosted production SaaS and should not be presented as a complete multi-document automation platform.
