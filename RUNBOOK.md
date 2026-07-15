# Runbook - AI Document Operations System

This runbook covers the local portfolio profile, optional real-provider verification, quality
gates, and safe cleanup.

## Prerequisites

- Python 3.11 or newer
- Node.js and npm
- PowerShell
- optional: Docker Desktop

Run commands from the repository root.

## Local Mock Demo

The mock profile requires no paid service or provider credential.

```powershell
.\scripts\setup_local_venv.ps1

Push-Location frontend
npm ci
npm run build
Pop-Location

.\scripts\start_dev.ps1
```

Open `http://127.0.0.1:8000`. Use the local demo token defined by `.env.example` (`123`).

The startup script uses `.env` when present and `.env.example` otherwise. Local runtime state is
written under `backend/data/`, which is ignored by Git.

Health checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

## Real Provider Profile

Create the ignored local configuration once:

```powershell
Copy-Item .env.example .env
```

Set these values in `.env` without placing credentials in commands or documentation:

```dotenv
PARSER_PROVIDER=mistral
MISTRAL_API_KEY=
MISTRAL_OCR_ENDPOINT=https://api.mistral.ai/v1/ocr
MISTRAL_OCR_MODEL=mistral-ocr-latest

EXTRACTOR_PROVIDER=openai_compatible
EXTRACTOR_API_KEY=
EXTRACTOR_ENDPOINT=https://api.groq.com/openai/v1/chat/completions
EXTRACTOR_MODEL=llama-3.3-70b-versatile
```

Keep `APP_ENV=local`. Do not commit `.env`, provider responses containing sensitive content, or
real invoice PDFs.

Verify provider adapters with a safe invoice:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe scripts\smoke_providers.py sample_invoice.pdf
```

Then start the app and exercise the full UI flow. A successful extraction must still stop for a
reviewer decision.

## Synthetic Scenario Evaluation

The committed dataset contains 20 safe synthetic PDFs.

```powershell
$env:BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS = "20"
.\.venv\Scripts\python.exe scripts\run_real_fixture_extraction.py `
  "$env:TEMP\invoice-scenarios-predicted.json" `
  --dataset examples\benchmark\datasets\invoice_scenarios_v1 `
  --report "$env:TEMP\invoice-scenarios-report.json"
```

Real-provider results vary with network and provider changes. Compare the output with
`docs/invoice-scenarios-v1-evidence.md` and report new failures rather than overwriting them.

## Private External Evaluation

Store licensed external invoices outside the repository, for example:

```text
C:\Users\William\Documents\Private Datasets\ai-document-ops-system\external_invoice_holdout_v1
```

Keep the raw PDFs, golden labels, OCR text, provider responses, and correction logs private. If a
tool temporarily requires a repository-relative path, use `_private_data/`; Git, Docker, and the
public-artifact packager exclude that directory.

Only aggregate metrics, sanitized failure examples, dataset citations, and license attribution may
be committed. Check `git status` and inspect the generated public artifact before every release.

## Quality Gates

Backend:

```powershell
$env:ENV_FILE = ".env.example"
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m unittest discover -s backend/app/tests -t backend
.\.venv\Scripts\python.exe -m ruff check backend scripts
```

Frontend:

```powershell
Push-Location frontend
npm test
npm run lint
npm run build
Pop-Location
```

Public artifact:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_public_artifact.py `
  "$env:TEMP\ai-document-ops-public"
```

Review the generated directory before sharing it.

## Docker Profile

```powershell
.\scripts\start_docker.ps1
```

The default compose profile runs the API, worker, SQLite metadata, and local private document
storage. The optional Postgres service documents a target topology; it is not the active runtime
repository implementation.

See `docs/docker_profile.md` for the local service boundary and `docs/aws_deployment.md` for an
explicitly unimplemented hosted target architecture.

## Safe Local Reset

Stop the API and worker before resetting. These files contain only local runtime state when the
documented configuration is used:

```powershell
Remove-Item -LiteralPath "backend\data\doc_intel.sqlite3" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "backend\data\uploads" -Recurse -Force -ErrorAction SilentlyContinue
```

Never run cleanup against an unverified custom `SQLITE_PATH` or `UPLOAD_ROOT`.

## Troubleshooting

### Frontend is not served

Run `npm run build` in `frontend/`, then restart the API. FastAPI serves `frontend/dist` when it
exists.

### PDF preview is blank

Confirm the document content request returns `application/pdf`, the session is authenticated,
and the browser console has no CSP or worker error. Use the explicit open-PDF action as a fallback
while diagnosing rendering.

### Invoice is not in Approvals

Check its business status. Processing invoices are still being read; correction-required
invoices remain separate from clean invoices waiting for a reviewer decision.

### Provider request fails

Check `/providers/health`, endpoint/model compatibility, credential validity, and
`PROVIDER_TIMEOUT_SECONDS`. Authentication failures are non-retryable. Rate limits and supported
server failures use the bounded processing retry path.

## Operating Boundary

This is a local-first portfolio system. Do not present the Docker profile, security middleware,
or synthetic benchmark as evidence of a production deployment or customer validation.
