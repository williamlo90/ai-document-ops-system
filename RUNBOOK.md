# Runbook - AI-Powered Invoice Review & Approval System

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
They also require a persistent `STORAGE_BACKEND` (`sqlite` or `postgres`); the in-memory backend is
disposable test state and is rejected during hosted startup.

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
storage. API, worker, and migration services use the same image as the non-root `docintel` user,
drop Linux capabilities, enable `no-new-privileges`, and use a read-only root filesystem with
bounded writable mounts for `/tmp` and `/data`.

To exercise the PostgreSQL runtime locally:

```powershell
docker compose --profile postgres-target up -d postgres-target
$env:DATABASE_URL = 'postgresql://docintel:docintel@127.0.0.1:5432/docintel'
.\.venv\Scripts\python.exe scripts\postgres_migrate.py
Remove-Item Env:DATABASE_URL
```

The migration command reads `DATABASE_URL` from the environment so credentials do not appear in
the process command line. The equivalent one-shot Compose mode is:

```powershell
docker compose --profile migrate run --rm migrate
```

Then set `STORAGE_BACKEND=postgres` and `DATABASE_URL` before starting the API and worker. Apply
migrations before either process starts. `DATABASE_POOL_SIZE`,
`DATABASE_CONNECT_TIMEOUT_SECONDS`, and `DATABASE_ACQUIRE_TIMEOUT_SECONDS` bound database resource
use and wait time.

The PostgreSQL adapter supports shared API/worker state and atomic job claims. Sessions and request
rate limits remain process-local, so production must run exactly one API replica until those two
controls move to a shared store. Multiple worker replicas are supported.

### Production-validation harness

Use the validation overlay to exercise the paced workload against the local Docker/PostgreSQL
profile with deterministic providers. It deliberately uses `.env.example`, not a developer `.env`
that may select paid providers:

```powershell
$env:DOC_INTEL_ENV_FILE = ".env.example"
docker compose -f docker-compose.yml -f docker-compose.validation.yml `
  --profile postgres-target up -d --build postgres-target
docker compose -f docker-compose.yml -f docker-compose.validation.yml `
  --profile migrate run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.validation.yml `
  --profile postgres-target up -d api worker

$env:PRODUCTION_VALIDATION_ACCESS_TOKEN = "123"
.\.venv\Scripts\python.exe -m scripts.production_validation.run `
  --confirm-synthetic-target `
  --target-label local-postgres `
  --duration-seconds 60 `
  --read-users 2
Remove-Item Env:PRODUCTION_VALIDATION_ACCESS_TOKEN
```

The runner records p50/p90/p95/p99, status distribution, throughput, one-minute windows, frozen
acceptance checks, and upload-ID invariants. Reports are written below ignored
`_local_docs/azure/production-validation/<run-id>/`; authentication credentials and the target URL
are never serialized. A local rehearsal verifies the harness only. The `pg01` profile additionally
enforces the frozen 60-minute/10-user workload and is reserved for the controlled Azure run.

The live-test controls are opt-in and absent from HTTP routing. Runtime deployment keeps alerts,
the internal ambiguous-outcome sink, and the manual claim-and-exit job disabled unless their
individual switches are supplied. The notification address and sink secret are secure/local
parameters and must never be committed.

The guarded recovery command requires an exact validation run ID, exact job ID, production mode,
the `azure-validation` workspace, mock providers, and two explicit confirmations:

```powershell
.\infra\azure\scripts\claim-and-exit.ps1 `
  -JobId <queued-job-id> `
  -RunId <validation-run-id> `
  -ConfirmLeaseAbandonment `
  -ConfirmBillable
```

Queue poison/replay and trace checks are operator commands under `scripts/production_validation/`.
DLQ replay refuses to proceed if any inspected dead-letter message is not tagged with the exact
validation run ID. `trace_probe.py` requires API completion, queue publication, worker disposition,
and terminal processing evidence for the same trace ID before it passes.

### Immutable image and runtime verification

Every image carries OCI source, revision, and creation labels. A release candidate must be built
from clean container build inputs so its content maps to one Git commit. Untracked files outside
the explicit Dockerfile inputs do not affect the image:

```powershell
.\.venv\Scripts\python.exe scripts\build_release_image.py
```

The command refuses modified or untracked build inputs and tags the image with the full commit SHA.
After pushing to ACR, deploy the registry digest (`repository@sha256:...`), never a mutable tag.

Verify all three runtime modes, read-only filesystems, liveness/readiness behavior during a
PostgreSQL outage, and graceful API/worker `SIGTERM` handling:

```powershell
.\.venv\Scripts\python.exe scripts\container_runtime_smoke.py `
  --image ai-document-ops-system:<full-git-sha> `
  --expected-revision <full-git-sha>
```

The script creates isolated, randomly named Docker resources and removes them on completion. CI
runs the same smoke before scanning the frozen image with Trivy. Fixed HIGH or CRITICAL findings
fail the build; unfixed findings are reported but cannot be remediated in the image and follow the
documented dependency-review process.

The Phase E Azure runtime templates under `infra/azure/container-apps/` remain a readable contract.
The deployable Phase F implementation is under `infra/azure/`: subscription-scope foundation,
resource-group runtime, Event Grid activation, small Bicep modules, a Flex Consumption ingestion
Function, and guarded PowerShell operations. API, worker, migration, and ingestion have separate
Managed Identities and role assignments. Runtime image references must be registry digests, and no
deployment output contains a secret value.

Start with `infra/azure/ACCOUNT_SETUP.md` only after local Bicep validation is complete. The scripts
have three deliberate safety levels: `preflight.ps1` is read-only, `provision.ps1` and
`deploy-runtime.ps1` default to Azure `what-if`, and billable mutations require both `-Apply` and
`-ConfirmBillable`. Teardown accepts only a narrowly named AI Document resource group and requires
`-ConfirmDestroy`; use `-Wait` to prove that Azure reports the group absent.

The validation profile favors short lifetime and evidence collection over production HA. The API
stays at one replica, the worker scales from zero, PostgreSQL uses a small Burstable SKU, and every
taggable resource carries a source revision plus expiration timestamp. The PostgreSQL
Azure-services-only firewall is a documented short-run compromise; a long-running production
environment should use private networking. Expiration tags do not delete resources automatically.
Always collect sanitized evidence, inventory the exact group, and run guarded teardown.

### Azure Blob storage profile

Run the local Azure Blob emulator without an Azure account:

```powershell
docker compose --profile azure-blob up -d azure-blob-emulator
```

For a host-run API, configure the ignored `.env` with:

```dotenv
DOCUMENT_STORAGE_BACKEND=azure-blob
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
AZURE_STORAGE_CONTAINER=documents
AZURE_STORAGE_CREATE_CONTAINER=true
```

Production uses a pre-created private container and Managed Identity:

```dotenv
DOCUMENT_STORAGE_BACKEND=azure-blob
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER=documents
AZURE_STORAGE_CREATE_CONTAINER=false
```

Assign the runtime identity Blob Data Contributor access at container scope. The adapter uses
`DefaultAzureCredential`; no storage account key or connection string is required in the production
container. Browser downloads continue through the authenticated application route rather than an
anonymous blob URL.

Source invoices are removed through the application retention workflow so blob deletion and the
audited metadata tombstone remain coordinated. `DOCUMENT_RETENTION_DAYS` controls source retention,
and `PARSER_CACHE_RETENTION_HOURS` controls the bounded local parser cache. Do not apply an
independent lifecycle deletion rule to source invoice prefixes.

### Azure Service Bus processing profile

The processing queue carries wake-up commands only. PostgreSQL remains authoritative for job
status, attempts, retry deadlines, and worker leases. A queue outage therefore degrades event-driven
wake-ups but does not discard committed jobs; the worker continues using database polling.

Production uses Managed Identity:

```dotenv
PROCESSING_QUEUE_BACKEND=azure-service-bus
AZURE_SERVICE_BUS_NAMESPACE=<namespace>.servicebus.windows.net
AZURE_SERVICE_BUS_CONNECTION_STRING=
AZURE_SERVICE_BUS_QUEUE_NAME=document-processing
AZURE_SERVICE_BUS_TIMEOUT_SECONDS=30
AZURE_SERVICE_BUS_MAX_LOCK_RENEWAL_SECONDS=300
AZURE_SERVICE_BUS_MAX_DELIVERY_COUNT=5
```

Grant the API/worker identity Azure Service Bus Data Sender and Data Receiver roles at queue or
namespace scope. Configure the queue with a one-minute lock, maximum delivery count `5`, and a
one-hour default TTL. Messages contain identifiers and a trace ID, never filenames, OCR text, or
invoice fields.

The optional local emulator requires Docker, at least 2 GB free RAM, and explicit acceptance of
Microsoft's Service Bus Emulator and SQL Server license terms. After reviewing those terms, put a
strong local-only SQL password and the acceptance flag in an ignored `.env`, then run:

```powershell
docker compose --profile service-bus up -d service-bus-sql service-bus-emulator
```

For an API/worker running on the host, use this documented emulator connection string in the
ignored `.env`:

```dotenv
PROCESSING_QUEUE_BACKEND=azure-service-bus
AZURE_SERVICE_BUS_CONNECTION_STRING=Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;
AZURE_SERVICE_BUS_QUEUE_NAME=document-processing
```

For application containers on the Compose network, replace `localhost` with
`service-bus-emulator`. The emulator is development-only, has no SLA, does not persist queue state
across restarts, and does not validate Managed Identity behavior.

Run the broker integration contract explicitly:

```powershell
$env:SERVICE_BUS_TEST_CONNECTION_STRING='Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;'
.\.venv\Scripts\python.exe -m unittest backend.app.tests.test_azure_service_bus -v
Remove-Item Env:SERVICE_BUS_TEST_CONNECTION_STRING
```

Inspect poison messages in the queue's dead-letter subqueue. A valid duplicate message should
complete without increasing the PostgreSQL job attempt count. Retryable provider failures are
recorded in PostgreSQL with a bounded retry time and are recovered by the polling path.

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
server failures use the fixed-limit processing retry path.

## Operating Boundary

This is a local-first portfolio system. Do not present the Docker profile, security middleware,
or synthetic benchmark as evidence of a production deployment or customer validation.
