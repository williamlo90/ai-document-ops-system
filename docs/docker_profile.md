# Docker Profile

The repository includes a self-contained local Docker topology for reproducible demonstrations.

## Bounded seeded demo

After `scripts/setup_local_venv.ps1`, start Docker Desktop, then run:

```powershell
.\scripts\start_release.ps1 -Seed
```

This builds the image, starts API and worker, waits for readiness, authors a synthetic
PDF and seeds an AP review through HTTP. Open the printed review URL. The local role
tokens are `release-uploader`, `release-reviewer`, `release-approver` and `release-admin`.
The demo explicitly selects mock providers and disables ERP writes. It demonstrates
reviewed reference values and deterministic matching; it is not an OCR accuracy score.

The release overlay is `docker-compose.release.yml`. Its API has a 512 MiB / 1 CPU
limit; the worker has 384 MiB / 0.5 CPU. Both have PID limits, a read-only root,
dropped capabilities and no-new-privileges. The application binds to loopback.
`DOC_INTEL_PORT` can select another local port. The named volume
`invoice-review-release_docintel-data` persists the database and uploaded PDFs.

The older `scripts/start_docker.ps1` remains a general development entry point;
it can use the ignored `.env`. The bounded release entry point is preferred for demos.

## Repeatable checks

```powershell
.venv\Scripts\python.exe scripts/evaluate_phase1_regressions.py --output _local_docs/evaluator-regressions.json
.venv\Scripts\python.exe scripts/container_runtime_smoke.py --image invoice-review:phase7-local
```

The first command verifies the offline evaluator with controlled mutations, not provider
accuracy. The second runs API/worker/migrations on a temporary PostgreSQL network,
checks database-loss readiness, liveness and graceful shutdown, and removes its
containers/network. It uses bounded containers and leaves the demo volume intact.

After a completed checkpoint, build a clean, commit-labelled image with:

```powershell
.venv\Scripts\python.exe scripts/build_release_image.py
```

That command refuses dirty build inputs. Local validation images identify dirty sources
explicitly; the release evidence also binds the exact build inputs by SHA-256.

## PostgreSQL

SQLite remains the default demo store. PostgreSQL adapters and migrations are also
implemented and tested. Run the optional target only when needed:

```powershell
docker compose -p invoice-review-release -f docker-compose.yml -f docker-compose.release.yml --profile postgres-target up -d postgres-target
$env:DATABASE_URL='postgresql://docintel:docintel@127.0.0.1:5432/docintel'
.venv\Scripts\python.exe scripts/postgres_migrate.py
$env:POSTGRES_TEST_DATABASE_URL=$env:DATABASE_URL
$env:PYTHONPATH='backend'
.venv\Scripts\python.exe -m unittest app.tests.test_postgres_persistence app.tests.test_ap_postgres.PostgresPostingTests -v
```

These credentials are for the loopback development target. Migration runs are idempotent.
`docker-compose.validation.yml` selects PostgreSQL for the application itself;
`container_runtime_smoke.py` validates that runtime in isolation.

## Existing ERPNext sandbox

ERP integration requires the separately configured sandbox and verified master/profile
mappings in [ERPNext environment](erpnext-environment.md). Provider and ERP credentials
stay in the ignored env file selected by `DOC_INTEL_ENV_FILE`.

The optional `erp-sandbox` profile adds a 64 MiB bridge inside the API network namespace.
It listens only on `127.0.0.1:18080` and forwards to the existing local host sandbox.
No bridge port is published. The application's loopback-only plain-HTTP ERP policy is
unchanged. The bridge permits writes only for synthetic invoice numbers beginning `REL-`.
It is a local validation tool, not a hosted ERP transport.

```powershell
.venv\Scripts\python.exe scripts/phase7_provision_erp.py _local_docs/new-release-fixture
$env:DOC_INTEL_ENV_FILE='.env'
$env:RELEASE_ACCOUNTING_PROVIDER='erpnext'
$env:RELEASE_POSTING_ENABLED='true'
docker compose -p invoice-review-release -f docker-compose.yml -f docker-compose.release.yml --profile erp-sandbox up -d --no-build --wait api worker erp-bridge
```

Broad regressions use mock extraction. A separately bounded canary selects
`RELEASE_PARSER_PROVIDER=ocr_space` and `RELEASE_EXTRACTOR_PROVIDER=llm_json`.
A canary uses one new synthetic PDF and preserves its original values. It never
reprocesses an answer for a better score; `--document-id` resumes review of the same
PDF/extraction after checking its hash. No payment is created.

## Rollback, backup and teardown

Set `RELEASE_POSTING_ENABLED=false` and recreate API/worker/bridge with the same
Compose command to stop new writes. Keep the same volume, ERP credentials and URL.
Known operations, approvals and reservations remain. Approvers can reconcile a known
`unknown` operation through read-only ERP lookups while writes stay disabled.
Never replace an unknown operation with a fresh invoice or drop its ledger.

For a consistent local backup/restore drill, stop API and worker first:

```powershell
docker compose -p invoice-review-release -f docker-compose.yml -f docker-compose.release.yml --profile erp-sandbox stop api worker erp-bridge
.venv\Scripts\python.exe scripts/phase7_storage_drill.py --output _local_docs/storage-drill.json
```

The drill copies SQLite and uploads, restores to a new directory in the same local
volume, checks integrity/foreign keys, hashes business/audit/AP rows and uploaded
objects, and leaves the original data intact. This tests local restoration, not
independent off-host disaster recovery or ERP database backup. Copy an approved
backup to separate protected storage for an actual recovery policy.

Stop the release project without deleting its volume:

```powershell
docker compose -p invoice-review-release -f docker-compose.yml -f docker-compose.release.yml --profile erp-sandbox --profile postgres-target stop
```

Do not use `down -v` to resolve an unknown ERP outcome. ERPNext is a separate project
and must be stopped separately when finished. See [Phase 7 evidence](evidence/invoice-review-v2/PHASE-7.md).

## Boundary

Docker packaging does not make the system production-ready. These checks establish
local synthetic release behavior. Hosted ingress, managed secrets/identity, durable
backups, concurrent workload capacity and customer data require separate validation.
