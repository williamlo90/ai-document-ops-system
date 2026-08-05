# Docker Profile

The repository includes a self-contained local Docker topology for reproducible demonstrations.

## Default Services

```powershell
.\scripts\start_docker.ps1
```

- `api`: FastAPI application on port `8000`
- `worker`: polling worker running `python -m app.worker_loop`
- `docintel-data`: shared named volume for local metadata and private uploads

The API and worker use the same environment file and storage volume.

## Runtime Mode

The default local settings use SQLite and private local document storage:

```text
STORAGE_BACKEND=sqlite
SQLITE_PATH=/data/doc_intel.sqlite3
UPLOAD_ROOT=/data/uploads
DOCUMENT_STORAGE_BACKEND=local
```

## Postgres Target Profile

```powershell
docker compose --profile postgres-target up postgres-target
```

This service documents an intended database topology only. The application runtime does not yet
use a Postgres repository adapter, so the profile must not be presented as an active production
database implementation.

## Smoke Check

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

## Boundary

Docker packaging does not make the system production-ready. A hosted deployment still requires
managed identity, secrets, tenant lifecycle, Postgres-backed repositories, object storage,
monitoring, backups, and HTTPS ingress.
