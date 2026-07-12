# Baseline Verification

Status: Main Sprint 0 baseline captured 2026-07-08 (Asia/Jakarta).

## Environment

- Workspace: `ai-document-ops-system` under the Agentic Project copy.
- Runtime: local SQLite/mock-first profile.
- Backend virtual environment: `.venv`.
- Frontend: React 19, Vite, TypeScript, Playwright.
- Real external credentials were not required or used.

## Backend

Recommended roadmap command could not run because `pytest` is not installed by `requirements.txt` or `requirements-dev.txt`:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/app/tests -q
# No module named pytest
```

The repository tests are compatible with the standard runner when the documented backend import path is set:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/app/tests -p "test_*.py" -q
```

Result: **351 passed, 2 skipped, 0 failed** in 20.340 seconds.

Observed non-blocking warning: Starlette deprecates its current `httpx` TestClient integration and recommends `httpx2`.

## Frontend

Commands run at the end of Frontend Sprint 6:

```powershell
npm test -- --run
npm run build
npm run test:e2e
npm run capture:portfolio
```

Results:

- Vitest: **4 passed**.
- TypeScript/Vite production build: **passed**.
- Playwright normal suite: **34 passed, 5 skipped by configuration** across desktop/tablet/mobile.
- Portfolio capture: **1 passed**; five current screenshots generated in `docs/assets/screenshots/`.

## Contract Gaps Confirmed

- At Sprint 0, FastAPI title still used the older `Doc Intel MVP` naming.
- `GET /documents/{id}/workflow` does not exist.
- `GET /invoices/{id}/workflow` is the current workflow projection endpoint.
- At Sprint 0, no persisted `document_type` or operation-template contract was found.
- Invoice remains the only complete evidence/validation schema.

Current update:

- Documents now expose `document_type` and supported schema metadata in the document APIs and workspace UI.
- FastAPI metadata now uses `AI Document Operations System`.
- Back-office AgentOps scenario datasets now include `document_type` and `operation_type` dimensions.
- Scenario evaluation results now persist expected and actual document/operation evidence for replay after refresh or app recreation.
- Operation templates remain invoice-backed; a second executable document workflow is still deferred.

## Baseline Decision

The application is healthy enough for additive migration. Main Sprint 1 may update safe backend metadata/documentation; Main Sprint 2 should then add the generic workflow projection while retaining invoice compatibility.
