# Runbook - Autonomous Backoffice AI

Project 4 extends the document operations platform with bounded autonomous back-office planning, drafts, approvals, controlled execution, and AgentOps evaluation.

## Local Quality Gate

```powershell
.\.venv\Scripts\python.exe -m black --check backend scripts run_tests.py
.\.venv\Scripts\python.exe -m ruff check backend scripts run_tests.py
.\.venv\Scripts\python.exe run_tests.py
docker compose config --quiet
cd frontend
npm run lint
npm run build
```

## Local React UI Run

Install dependencies once if this is a fresh checkout:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
cd frontend
npm install
cd ..
```

Terminal 1:

```powershell
$env:ENV_FILE='.env.example'
$env:PYTHONPATH='backend'
$env:UPLOAD_ROOT='backend/data/uploads'
$env:SQLITE_PATH='backend/data/doc_intel.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173
```

Use `change-me-for-local-demo` as the local demo admin token unless you override it.

## Local Docker Run

```powershell
docker compose config --quiet
docker compose up --build
```

Open:

```text
http://127.0.0.1:8000
```

This is the production-shaped one-command path: Docker builds the React bundle,
serves it from FastAPI on the same origin, starts the API, and starts the durable
worker process. Use `Ctrl+C`, then `docker compose down`, for graceful local
shutdown.

Runtime diagnostics:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/internal/metrics
```

Responses include `X-Request-ID` and `X-Trace-ID` for correlation with JSON
stdout logs. `/health` is liveness; `/ready` checks traffic acceptance, database,
and storage and returns HTTP 503 when the API is draining or a dependency fails.
`docker compose stop` sends SIGTERM. Uvicorn gets a 30-second graceful deadline,
and the worker finishes its current job attempt before exiting.

Development mode can use:

- `http://127.0.0.1:5173` for the React development UI.
- `http://127.0.0.1:8000` for the production-shaped same-origin UI after `npm run build`.
- `/ui` for server-rendered fallback document upload, processing, review, export, and trace-seeding access.
- `/ui/backoffice` for server-rendered backoffice workflow diagnostics.
- `/ui/agentops` for reliability metrics and scenario evidence.

## Agent Safety Checks

When implementing autonomous behavior, verify:

- read-only tools do not mutate state
- mutation tools require confirmation
- low-confidence recommendations escalate to a human
- recommendations include why-not explanations when alternatives are unsafe
- workspace scoping still works
- role checks still work
- failure types use the Project 3 taxonomy
- blocked actions are logged with reasons
- no secret/storage path leaks appear in responses
- back-office work items stay workspace scoped
- risky Project 4 actions show approval controls before execution
- Project 4 scenarios remain replayable through AgentOps

## Backoffice Scenario Checks

```powershell
Invoke-RestMethod http://127.0.0.1:8000/agentops/backoffice/scenarios `
  -Headers @{ "X-Admin-Token"="change-me-for-local-demo" }
```

The dataset is also stored at:

```text
examples/agentops/project4_scenarios_v1.json
```

## Current Boundary

Project 4 is not a full autonomous ERP or hosted production SaaS. It is a production-shaped local platform that demonstrates bounded autonomy, human approvals, controlled tool execution, and reliability measurement.

For deployment gaps and the staged cloud path, see `docs/docker_profile.md`
and `docs/aws_deployment.md`. Object-storage notes live in
`docs/object_storage.md`.
