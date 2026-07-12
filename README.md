# AI Document Operations System

Local-first document operations for invoice intake, extraction, deterministic validation,
exception review, approval-gated execution, durable audit activity, and technical evidence.

Invoice is the first fully supported document type. The architecture is designed for additive
document-type adapters, but the current product does not claim complete non-invoice workflows.

## Source Baseline

Project 4 starts from:

```text
../3.5-agentops-reliability-dashboard-github-refactored
```

Project 3.5 remains the source of truth for reliability measurement, scenario evaluation, planning version comparison, regression comparison, and AgentOps trace behavior.

For real provider, email, object storage, and PostgreSQL/Supabase setup, see
[`docs/integrations.md`](docs/integrations.md), [`docs/object_storage.md`](docs/object_storage.md),
and [`docs/aws_deployment.md`](docs/aws_deployment.md).

## Product Thesis

```text
AI-assisted document operations are valuable when evidence is visible, deterministic rules gate
execution, risky actions require approval, and uncertain work returns to a human.
```

## What The System Provides

- business-facing invoice intake for upload, system reading, review, approval or rejection, and history
- reviewer queue with explicit human approval before export-ready work
- controlled execution policies for safe versus risky actions
- back-office planning and draft/execution APIs kept behind approval boundaries
- simplified React UI for uploader and reviewer roles, with technical evidence kept out of the main user path
- System Reliability, Reliability Checks, Test Scenarios, and Run Traces for local technical evidence
- Project 4 repeatable test scenarios for multi-step document work
- deployment readiness plan for Docker, CI, and future cloud delivery

## What Project 4 Must Preserve

- Project 2 workflow enforcement
- Project 3 tool contracts and confirmation boundaries
- Project 3 human escalation behavior
- Project 3.5 AgentOps evaluation engine
- Project 3.5 prompt and scenario versioning
- Project 3.5 regression comparison
- honest local-first portfolio scope

## Current Limitations

- unrestricted autonomy
- production SaaS readiness
- real customer deployment
- billing-ready multi-tenant product
- fully automated finance operations without human approval

## Local Demo

The default profile uses SQLite, local storage, deterministic/mock providers, and no paid
credentials. See `RUNBOOK.md` for startup commands and `docs/assets/screenshots/` for current UI
captures.

Fast local start after dependencies are installed:

```powershell
$env:ENV_FILE='.env.example'
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Read First

- `PRD.md`
- `ROADMAP.md`
- `ARCHITECTURE.md`
- `UI_PLAN.md`
- `RUNBOOK.md`
- `docs/pivot/FEATURE_API_MATRIX.md`
- `docs/pivot/COMPATIBILITY_ALIASES.md`
- `docs/final-release-notes.md`
