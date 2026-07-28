# Runbook - Invoice Review

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

Open `http://127.0.0.1:8000`. Use `uploader-123` for invoice intake or `reviewer-123` for the
review queue. The local admin credential remains `123`. These values are local-only; hosted modes
reject weak or duplicate credentials.

The startup script uses `.env` when present and `.env.example` otherwise. Local runtime state is
written under `backend/data/`, which is ignored by Git.

Health checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Prometheus metrics require a credential that cannot access business APIs:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/internal/metrics `
  -Headers @{ "X-Metrics-Token" = "metrics-123" }
```

Hosted modes require `APP_METRICS_TOKEN` to contain at least 24 non-default characters and to be
different from every user-role credential. Keep the route off public ingress even with this control.

## Real Provider Profile

Create the ignored local configuration once:

```powershell
Copy-Item .env.example .env
```

Set these values in `.env` without placing credentials in commands or documentation:

```dotenv
PARSER_PROVIDER=mistral_ocr
MISTRAL_API_KEY=
MISTRAL_OCR_ENDPOINT=https://api.mistral.ai/v1/ocr
MISTRAL_OCR_MODEL=mistral-ocr-latest
MISTRAL_ALLOWED_HOSTS=api.mistral.ai

EXTRACTOR_PROVIDER=llm_json
EXTRACTOR_API_KEY=
EXTRACTOR_ENDPOINT=https://api.openai.com/v1/chat/completions
EXTRACTOR_MODEL=gpt-5.4-mini-2026-03-17
EXTRACTOR_ALLOWED_HOSTS=api.openai.com
```

Keep `APP_ENV=local`. Do not commit `.env`, provider responses containing sensitive content, or
real invoice PDFs.

Provider endpoints must use HTTPS on the default port, match an exact host in the corresponding
allowlist, and contain no URL credential, query, or fragment. HTTP redirects are rejected rather
than followed. Do not add a proxy or replacement provider host until its data-governance decision is
recorded in [Provider Data Boundary](docs/security/provider-data-boundary.md).

Verify provider adapters with a safe invoice:

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe scripts\smoke_providers.py sample_invoice.pdf
```

Then start the app and exercise the full UI flow. A successful extraction must still stop for a
reviewer decision.

## Upload Scanning And Retention

The local and controlled synthetic-demo profiles use the built-in signature guard. It proves the
scanner boundary and EICAR rejection path, but it is not a production antivirus engine. Production
mode fails startup unless these settings select ClamAV:

```dotenv
MALWARE_SCANNING_ENABLED=true
MALWARE_SCANNER_BACKEND=clamav
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CLAMAV_TIMEOUT_SECONDS=10
```

The ClamAV adapter uses the `INSTREAM` protocol and fails the upload closed with `503` when the
scanner cannot verify it. Verify network isolation, signature updates, health monitoring, and an
EICAR upload in the authorized deployment before accepting untrusted PDFs.

Retention defaults to 90 days for terminal documents and 24 hours for downloaded parser-cache
files. Inspect candidates without deleting data:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/operations/retention" `
  -Headers @{ "X-Access-Token" = "123" }

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/operations/retention/purge" `
  -ContentType "application/json" `
  -Body '{"dry_run":true,"reason":"retention_policy"}' `
  -Headers @{ "X-Access-Token" = "123" }
```

Only an administrator can execute purge. Deletion reason codes accept lowercase letters, numbers,
underscores, and hyphens so free-text invoice data does not enter access or audit logs. A purge
removes the document object, S3 parser cache,
core metadata, extraction, review, correction, workflow, notification, and document audit records.
It retains only a hashed document fingerprint and deletion counts as the purge tombstone. Database
backups and object-store version history require separate infrastructure lifecycle controls.

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

### Maintainable Experiment Record

Create a new 25-document pack without reusing layouts from an earlier private manifest:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_private_external_invoice_pack.py `
  <FATURA.zip> <private-pack-v2> `
  --pack-version v2 `
  --exclude-manifest <private-pack-v1\manifest.json>
```

Run diagnostic work first. `--document-id` is allowed only for targeted diagnostic debugging and
is rejected for holdout runs:

```powershell
.\.venv\Scripts\python.exe scripts\run_private_external_evaluation.py `
  <private-pack-v2> <sanitized-diagnostic.json> `
  --split diagnostic --rate-limit-seconds 2

.\.venv\Scripts\python.exe scripts\run_private_external_evaluation.py `
  <private-pack-v2> <sanitized-holdout.json> `
  --split holdout --rate-limit-seconds 2
```

Every invocation appends a manifest and result reference to the private
`evaluation_runs/experiment_index.jsonl`. Preserve failed runs. Commit only reviewed aggregate
JSON, never the private ledger, OCR text, predictions, labels, PDFs, or `.env`. See
`docs/evaluation-experiment-protocol.md` for the freeze and claim rules.

## Quality Gates

Run the complete release gate from a clean worktree:

```powershell
.\.venv\Scripts\python.exe scripts\verify_release.py --write-evidence
```

It runs the backend and frontend dependency, format, lint, test, build, complexity, fixture-browser,
and real full-stack browser checks. A passing clean run writes
`docs/evidence/release-verification.json`. Use a dry run while editing:

```powershell
.\.venv\Scripts\python.exe scripts\verify_release.py
```

The frontend dependency gate uses `npm run audit`, which performs a full npm audit and accepts only
the narrow, expiring advisory exception documented in
`docs/security/supply-chain.md`. Do not replace it with a claim that the dependency graph has no
advisories.

To record a current-provider diagnostic against the committed synthetic scenarios:

```powershell
.\.venv\Scripts\python.exe scripts\run_current_provider_evaluation.py `
  docs\evidence\current-provider-diagnostic.json `
  --max-documents 20
```

This command requires a clean worktree and configured Mistral and OpenAI credentials. It records
provider, model, prompt, code, dataset, cost, latency, and failure metadata, but deliberately labels
the result as a diagnostic rather than a blind holdout.

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
