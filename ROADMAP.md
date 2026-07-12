# Project 4 Roadmap - Autonomous Backoffice AI

This roadmap is the single source of truth for Project 4.

Project 4 continues from Project 3.5. It should preserve the document workflow, copilot guardrails, and AgentOps reliability layer while adding bounded autonomous back-office workflow orchestration.

## Current Status

```text
Current phase: Step 0 through Step 9 complete; document-operation refactor and UX simplification are complete for the invoice-first workflow; backend role-contract alignment is complete for uploader-owned invoice intake; backend approval source-of-truth alignment is complete; backoffice export execution guardrails are complete; reviewer API role hardening is complete; workspace ownership boundary hardening is complete; a second executable document workflow remains intentionally deferred
Source baseline: ../3.5-agentops-reliability-dashboard-github-refactored
Active agents: Codex only
Latest verification: full backend suite passed with 364 tests OK and 2 skipped; focused backend lint and format checks passed for the workspace ownership boundary hardening changes; frontend tests, lint, and production build passed; Docker compose config passed; public artifact packaging script passed in a temp output folder
Single source of truth: this ROADMAP plus `docs/pivot/*`; local-only completion TODO files are intentionally excluded from the public artifact
```

## Active Completion Backlog

- Keep generic `/documents/*` contracts additive while preserving invoice compatibility aliases; generic workflow projection is already covered by parity tests.
- Preserve role-scoped invoice intake: uploader/intake/operator roles may upload and process their own invoices, while reviewer approval remains separate from upload permissions.
- Preserve approval as an explicit reviewer action: processing may extract and validate invoices, but it must not mark invoices approved or export-ready.
- Re-check linked invoice approval at execution time for backoffice export steps; stale plans or approvals must not execute export work for an unapproved invoice.
- Keep reviewer API access role-specific: reviewer may list/save/approve/reject review items without admin access, while operator/intake/uploader roles must be forbidden from review decisions.
- Preserve workspace ownership boundaries: backoffice linked documents, backoffice mutations, and reviewer decisions must not cross workspace boundaries.
- Preserve persisted `document_type`, supported schema metadata, and AgentOps document/operation evidence.
- Add a second executable document workflow only when extraction, validation, planning, execution, and evaluation contracts are all covered.
- Keep public artifact hygiene green: no `.env`, `.venv`, upload folders, SQLite files, cache folders, or local-only planning files.

## Consolidated Refactor Plan

Older standalone sprint plans have been folded into this roadmap and `UI_PLAN.md`.

Backend/product refactor order:

1. Preserve the generic document workflow projection and invoice compatibility aliases.
2. Keep extending document type taxonomy and operation templates beyond invoice defaults.
3. Add generic evidence serialization while preserving invoice validation.
4. Make work items, reviewer flows, and policy decisions document-operation aware.
5. Preserve AgentOps document/operation scenario evidence and add new cases only when behavior exists.
6. Keep provider, integration, and deployment readiness local-first and credential-late.
7. Run final hardening through backend tests, frontend tests, build, public artifact tests, and release docs.

Deferred:

- A second executable non-invoice workflow remains deferred until document type, evidence, validation, planning, execution, and AgentOps coverage are all strong enough.

## Operating Rules

- Roadmap first, PRD second, implementation third.
- Project 4 extends Project 3.5; it does not rebuild the platform.
- Autonomy must be policy-gated, not unrestricted.
- Risky actions require confirmation.
- Unsafe actions must be blocked with an explicit reason.
- Low-confidence work must escalate to a human.
- Drafted outbound work must be reviewable before execution.
- AgentOps must remain the measurement layer for autonomous behavior.
- Do not claim production SaaS before deployment, auth, tenancy, monitoring, backups, billing, and real users exist.

## Step 0 - Project Setup And Direction

Status: Complete

Goal:
Create Project 4 from the Project 3.5 release baseline and define the autonomous back-office direction.

Delivered:

- copied Project 3.5 public artifact into `4-autonomous-backoffice-ai`
- `README.md`
- `PRD.md`
- `ROADMAP.md`
- `ARCHITECTURE.md`
- initial back-office workflow, autonomy policy, and readiness notes that are now consolidated into this roadmap, `PRD.md`, `ARCHITECTURE.md`, and `docs/final-release-notes.md`
- Project 4 public artifact script metadata updated
- public artifact tests updated for Project 4 setup docs

Acceptance criteria:

- Project 4 has its own folder
- Project 3.5 remains the source baseline
- docs clearly explain that Project 4 adds bounded autonomy instead of unrestricted automation
- Project 3.5 AgentOps remains part of the architecture
- public artifact metadata no longer points to Project 3.5 readiness docs

Status:
Completed by Codex.

Verification:

- public artifact tests - 17 tests OK
- Black check for touched setup Python files - OK
- Ruff check for touched setup Python files - OK

## Step 1 - Baseline Verification

Status: Complete

Goal:
Prove the copied Project 3.5 baseline still runs before Project 4 implementation begins.

Deliverables:

- Black check
- Ruff check
- full test suite
- docker compose config check
- baseline notes if inherited issues appear

Acceptance criteria:

- inherited Project 3.5 behavior is green
- local environment requirements are documented
- any setup issue is fixed before back-office autonomy features are added

Delivered:

- Ran Black, Ruff, Docker compose config, and full test suite from `4-autonomous-backoffice-ai`.
- Used the Project 3 `.venv` interpreter because the copied public artifact intentionally excludes `.venv`.
- Confirmed the inherited Project 3.5 baseline remains green before adding Project 4 domain features.

Verification:

- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 272 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 2 - Backoffice Domain Model

Status: Complete

Goal:
Introduce first-class work items, task plans, action drafts, approvals, and policy decisions.

Deliverables:

- work item model
- task plan model
- action step model
- action draft model
- approval model
- policy decision model
- repository support for in-memory and SQLite persistence if needed

Acceptance criteria:

- work items are workspace-scoped
- plans can reference linked documents
- action steps record risk level and required approval
- tests cover model creation, persistence, and workspace isolation

Delivered:

- Added `app.backoffice.models`.
- Added work item domain objects with source type, work type, priority, status, linked document ids, business context, and current plan reference.
- Added task plan and action step objects with planner version, risk level, required approval, why-this, and why-not fields.
- Added action draft and approval records with explicit review status transitions.
- Added policy decision record with autonomy level, risk level, confirmation requirement, allowed/blocked result, and reason.
- Added `app.backoffice.repositories` with in-memory repositories for work items, plans, drafts, approvals, and policy decisions.
- Added tests for model behavior, in-memory persistence, and workspace scoping.

Verification:

- focused backoffice model tests - 7 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 279 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 3 - Autonomy Policy Engine

Status: Complete

Goal:
Define explicit rules for what the AI can inspect, recommend, draft, execute, or block.

Deliverables:

- autonomy level enum
- risk classification
- policy rules for each action type
- confirmation-required enforcement
- blocked-action reasons
- tests for safe, risky, and blocked actions

Acceptance criteria:

- read-only actions can proceed without mutation
- draft actions cannot cause external side effects
- controlled execution requires confirmation
- cross-workspace and unsupported actions are blocked
- policy decisions are auditable

Delivered:

- Added `app.backoffice.policy`.
- Added `ActionPolicyRule` for deterministic autonomy policy configuration.
- Added `ACTION_POLICY_RULES` covering every Project 4 `ActionType`.
- Added `AutonomyPolicyEngine.decide` to produce auditable `PolicyDecision` records.
- Implemented read-only, recommendation, draft, confirm-execute, and blocked autonomy rules.
- Implemented role gates, workspace boundary checks, cross-workspace target blocking, evidence sufficiency checks, explicit unsafe request blocking, and confirmation-required enforcement.
- Added clear unsupported-action error handling.
- Added tests for safe read-only behavior, draft side-effect boundaries, risky confirmation, admin-only export, workspace boundaries, insufficient evidence, unsafe action blocking, unsupported action handling, and rule coverage.

Verification:

- focused backoffice policy tests - 11 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 290 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 4 - Backoffice Planner

Status: Complete

Goal:
Create deterministic task planning for document-driven back-office workflows.

Deliverables:

- planner service
- planner version field
- work type classification
- plan generation for common workflows
- confidence and escalation reason
- why-this and why-not explanations

Acceptance criteria:

- planner can classify invoice review/export/follow-up workflows
- planner creates bounded steps instead of direct free-form execution
- missing evidence triggers human escalation
- tests cover normal, low-confidence, and invalid-state plans

Delivered:

- Added `app.backoffice.planner`.
- Added `PLANNER_VERSION` and `PlanningInput`.
- Added `BackofficePlanner` with deterministic work-type classification.
- Added bounded planning for invoice review, invoice export, accounting note, vendor follow-up, unsupported cases, and insufficient-evidence cases.
- Integrated the planner with `AutonomyPolicyEngine` so every action step inherits policy risk, approval, and blocking behavior.
- Added why-this and why-not explanations on planned action steps.
- Added low-confidence escalation behavior that avoids mutating steps.
- Added invalid export-state handling that blocks export when approved evidence is missing.
- Kept high-risk but valid export actions as `waiting_for_approval` with `high` risk instead of incorrectly marking them as unsafe.
- Added tests for invoice review classification, vendor follow-up drafts, approved export approval flow, blocked export without approval evidence, low-confidence escalation, cross-workspace blocking, and accounting note draft-only planning.

Verification:

- focused backoffice planner tests - 7 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 297 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 5 - Controlled Execution And Drafts

Status: Complete

Goal:
Allow Project 4 to draft and execute bounded actions through existing Project 3 tool contracts.

Deliverables:

- draft accounting note or outbound message
- preview-before-execution flow
- approval API
- controlled execution service
- audit event integration
- failure recovery behavior

Acceptance criteria:

- draft content is visible before approval
- execution uses existing tool contracts
- risky tools cannot execute without confirmation
- failed execution records safe error details
- tests prove no guardrail bypass

Delivered:

- Added `app.backoffice.services`.
- Added `BackofficeWorkflowService` orchestration layer for work item creation, planning, draft creation, approval request/review, and approved execution.
- Added `BackofficePlanResult` to expose created drafts and pending approvals.
- Added draft generation for accounting notes, vendor messages, and export previews.
- Added approval flow for high-risk actions.
- Added controlled execution mapping from Project 4 actions to existing Project 3 tools.
- Blocked execution when human approval is missing or rejected.
- Preserved workspace isolation for work items and approvals.
- Recorded policy decisions during planning.
- Added safe blocked responses for unmapped, blocked, or unconfigured execution paths.
- Added tests for draft preview creation, pending approvals, blocked execution before approval, execution after approval through controlled executor, rejected approval blocking, and cross-workspace isolation.

Verification:

- focused backoffice workflow service tests - 6 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 303 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 6 - Operator Inbox UI

Status: Complete

Goal:
Add a local UI for managing work items, plans, drafts, approvals, and autonomous run traces.

Deliverables:

- `/ui/backoffice` page
- work item list
- work item detail
- plan review panel
- draft preview panel
- approval and rejection controls
- AgentOps link for each autonomous run

Acceptance criteria:

- user can inspect pending autonomous work locally
- low-confidence cases are clearly escalated
- risky actions show confirmation controls
- UI does not expose secrets or private storage paths
- UI tests cover main render and approval paths

Delivered:

- Wired Backoffice repositories and workflow service into the app container for local UI use.
- Added `/ui/backoffice` behind the existing UI login cookie.
- Added work item creation with work type, linked document, and requested outcome.
- Added deterministic plan creation controls for evidence, export approval, and missing fields.
- Added work item list, pending approval list, selected work item detail, plan review, draft preview, approval status, and policy decision panels.
- Added approval and rejection controls for risky action steps.
- Added execute control that only appears after the linked approval is granted.
- Added UI navigation from the existing dashboard and AgentOps page.
- Added UI tests for the empty inbox state and the full export approval/execution path.

Verification:

- focused backoffice UI tests - 2 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend\app\ui.py backend\app\api\dependencies.py backend\app\tests\test_api.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend\app\ui.py backend\app\api\dependencies.py backend\app\tests\test_api.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 305 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 7 - Project 4 Evaluation Scenarios

Status: Complete

Goal:
Extend AgentOps with Project 4 multi-step workflow scenarios.

Deliverables:

- Project 4 scenario dataset
- expected work type
- expected plan steps
- expected policy decisions
- expected escalation behavior
- scenario evaluation service update

Acceptance criteria:

- scenarios cover read-only, draft, confirm-execute, blocked, and escalation cases
- scenario version is recorded
- regression comparison can compare autonomous behavior
- tests cover matched and mismatched plans

Delivered:

- Added `examples/agentops/project4_scenarios_v1.json`.
- Added `project4_backoffice` dataset version `v1` with 5 deterministic scenarios.
- Covered read-only invoice review, draft vendor follow-up, confirm-execute approved export, blocked premature export, and insufficient-evidence escalation.
- Added `app.agentops.backoffice_scenarios` for dataset loading, scenario lookup, and plan-vs-scenario evaluation.
- Evaluator checks workspace, work type, plan steps, step statuses, risk levels, policy decisions, human requirement, confidence, and escalation reason.
- Added `/agentops/backoffice/scenarios`.
- Added `/agentops/backoffice/scenarios/evaluate`.
- Updated Project 4 scenario contract and evaluation scope, now consolidated into AgentOps tests, dataset fixtures, this roadmap, and release notes.
- Added direct evaluator tests for matched and mismatched plans.
- Added API tests for scenario contract, evaluation, and workspace scoping.

Verification:

- focused backoffice scenario/API tests - 6 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 311 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 8 - Deployment Readiness Package

Status: Complete

Goal:
Prepare Project 4 as a credible full-stack AI + DevOps portfolio artifact.

Deliverables:

- Docker Compose validation
- CI quality gates
- production-readiness gap list
- future AWS/Kubernetes path
- runbook update
- portfolio demo script

Acceptance criteria:

- local deployment path is clear
- cloud path is honest and staged
- limitations are explicit
- no fake SaaS claim is made

Delivered:

- Added deployment readiness material, now consolidated into `RUNBOOK.md`, `docs/docker_profile.md`, and `docs/final-release-notes.md`.
- Documented local Docker Compose deployment path and smoke checks.
- Documented CI quality gates and local equivalents.
- Documented runtime configuration boundary for SQLite and local storage.
- Added explicit production-readiness gap list.
- Added staged cloud path for single-VM Docker, AWS production-shaped split, and Kubernetes.
- Added honest portfolio claim and anti-claims.
- Updated `RUNBOOK.md` for Project 4 local UI, back-office inbox, AgentOps, and scenario checks.
- Updated `docs/docker_profile.md` from Project 2 framing to Project 4 deployment boundary.
- Updated readiness material from pre-implementation notes to current implementation/deployment readiness, now consolidated into `RUNBOOK.md`, `docs/docker_profile.md`, and `docs/final-release-notes.md`.
- Updated `docs/demo-script.md` and `docs/portfolio-demo.md` for Project 4 walkthrough.
- Updated public artifact packaging rules for clean GitHub-ready artifacts.
- Added tests proving deployment docs and the Project 4 scenario dataset are packaged correctly.

Verification:

- focused deployment/public-artifact tests - 6 tests OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe scripts\quality_report.py` - OK, average complexity A
- `docker compose config --quiet` - OK
- `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 312 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Step 9 - Public Artifact And GitHub Refactored Copy

Status: Complete

Goal:
Create a clean Project 4 public artifact and sibling GitHub-ready folder.

Deliverables:

- Project 4 public artifact script update
- public artifact tests
- generated public artifact
- `../4-autonomous-backoffice-ai-github-refactored`
- cleanup check for secret, cache, database, upload, and local environment artifacts

Acceptance criteria:

- artifact includes backend, tests, docs, scenarios, Docker, CI, and quality scripts
- artifact excludes `.env`, `.venv`, cache folders, SQLite/db files, upload folders, and generated validation output
- copied folder can be validated independently

Delivered:

- Ran public artifact tests before packaging.
- Generated clean public artifact at `dist/public-autonomous-backoffice-ai`.
- Created sibling GitHub-ready folder at `../4-autonomous-backoffice-ai-github-refactored`.
- Copied the sibling folder from the generated public artifact instead of from the live workspace.
- Verified the copied folder includes backend, tests, docs, scenarios, Docker, CI, quality scripts, deployment readiness docs, and Project 4 scenario dataset.
- Verified the copied folder excludes `.env`, `.venv`, cache folders, SQLite/db files, upload folders, and runtime validation output.
- Validated the copied folder independently with Black, Ruff, Radon quality report, Docker Compose config, and full tests.

Verification:

- public artifact tests - 17 tests OK
- generated public artifact - OK
- leak check on `../4-autonomous-backoffice-ai-github-refactored` - OK
- copied folder Black check - OK
- copied folder Ruff check - OK
- copied folder quality report - OK, average complexity A
- copied folder Docker Compose config - OK
- copied folder `..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py` - 312 tests OK, 2 real-provider tests skipped because credentials are not set

Status:
Completed by Codex.

## Definition Of Done

Project 4 is complete when:

- Project 3.5 baseline remains green
- back-office work item model exists
- autonomy policy engine exists
- planner creates bounded task plans
- drafts require review before execution
- risky actions require confirmation
- unsafe actions are blocked
- low-confidence cases escalate to humans
- operator inbox UI exists
- AgentOps evaluates autonomous runs
- Project 4 scenarios are replayable
- deployment readiness docs exist
- public/GitHub-ready artifact can be created
