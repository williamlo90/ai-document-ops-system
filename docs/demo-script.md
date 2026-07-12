# Demo Script - Project 4

Use this script for a portfolio walkthrough of the Autonomous Backoffice AI platform.

## 1. Position The Project

Explain the portfolio arc:

- Project 1: build the Document Intelligence MVP.
- Project 1.5: add provider comparison and evaluation evidence.
- Project 2: production-shape the document operations platform.
- Project 2.5: document ownership, architecture, and business value.
- Project 3: add an agentic copilot over the workflow.
- Project 3.5: evaluate whether the copilot is reliable.
- Project 4: add bounded autonomous back-office workflows with approvals and repeatable reliability checks.

Use the honest claim:

```text
An autonomous back-office AI platform that plans document-driven work, drafts reviewable actions, requires human approval for risky execution, and measures reliability through local traces and repeatable scenario checks.
```

## 2. Start The Local System

```powershell
docker compose config --quiet
docker compose up --build
```

Open:

```text
http://127.0.0.1:8000
```

## 3. Create Copilot Traces

Start the app, sign in with the local demo token, then use the React operator
console for document intake and review. If you need legacy copilot trace seed
actions, open `/ui` briefly:

- Summarize workflow
- Explain selected document
- Recommend next action
- Execute with confirmation

The goal is to create trace evidence, not to demo another chatbot.

## 4. Show The Business Flow

Open:

```text
http://127.0.0.1:8000
```

Show:

- start as uploader and upload a sample invoice
- show that system reading sends the invoice to reviewer approval instead of auto-approval
- switch to reviewer and open the review queue
- inspect the extracted fields, validation issues, and source document
- approve or reject from the decision screen
- show invoice history so the audit trail is obvious
- show export readiness only after approval

## 5. Show Technical Evidence

Open:

```text
http://127.0.0.1:8000/ui/agentops
```

Point out:

- System Reliability cards
- Run Traces / Decision Trace
- expected action versus actual action
- correctness field
- confidence
- known weak spot
- selected run detail
- tool-call timeline
- safe decision reason

## 6. Show API Evidence

Use API endpoints if the reviewer wants the raw contract:

```powershell
curl.exe http://127.0.0.1:8000/agentops/summary `
  -H "X-Admin-Token: 123"

curl.exe http://127.0.0.1:8000/agentops/runs `
  -H "X-Admin-Token: 123"

curl.exe http://127.0.0.1:8000/agentops/scenarios `
  -H "X-Admin-Token: 123"

curl.exe http://127.0.0.1:8000/agentops/backoffice/scenarios `
  -H "X-Admin-Token: 123"
```

Show that metrics come from traces, not from invented claims.

## 7. Show Test Scenarios

Open:

```text
examples/agentops/scenarios_v1.json
examples/agentops/project4_scenarios_v1.json
```

Explain:

- test set id: `agentops_core`
- test set version: `v1`
- scenarios cover read-only, recommendation, controlled execution, blocked action, cross-workspace, and escalation cases
- Project 4 dataset id: `project4_backoffice`
- Project 4 scenarios cover read-only planning, draft workflow, confirm-execute, blocked export, and insufficient-evidence escalation
- future planning or routing changes can be compared against the same scenario version

## 8. Show Deployment Readiness

Open:

```text
docs/docker_profile.md
docs/aws_deployment.md
```

Show:

- local Docker path
- CI quality gates
- production-readiness gaps
- staged AWS path
- staged Kubernetes path
- honest non-SaaS boundary

## 9. Show Regression And Prompt Version Concepts

Explain that Project 3.5 is designed to answer:

```text
Did the latest run window improve or regress compared with the previous one?
Did prompt version A behave better than prompt version B?
```

Current implementation uses deterministic `deterministic-v1`, but the comparison structures are already in place for future LLM prompt versions.

## 10. Show Quality Evidence

Run or cite:

```powershell
..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py
..\3-agentic-docops-copilot\.venv\Scripts\python.exe -m ruff check --no-cache backend scripts run_tests.py
docker compose config --quiet
..\3-agentic-docops-copilot\.venv\Scripts\python.exe run_tests.py
```

Latest verified result:

```text
311 tests OK, 2 real-provider tests skipped because credentials are not set.
```

## 11. Close With Scope

Say clearly:

- this is local bounded autonomy, not a hosted production SaaS
- metrics and scenarios are trace-derived
- LLM judge evaluation is intentionally out of scope for this slice
- cloud deployment requires the staged work listed in `docs/docker_profile.md` and `docs/aws_deployment.md`
