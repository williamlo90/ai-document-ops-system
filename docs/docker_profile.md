# Docker Profile

Project 4 includes a local production-shaped Docker topology inherited from the document workflow platform and extended by the back-office autonomy layer.

## Default Services

```powershell
scripts\start_docker.ps1
```

The default compose profile starts:

- `api`: FastAPI app exposed on port `8000`
- `worker`: polling worker that runs `python -m app.worker_loop`
- `docintel-data`: shared named volume mounted at `/data`

The API and worker use the same env file and share the same metadata/upload volume.

## Runtime Mode

The default `.env.example` uses:

```text
STORAGE_BACKEND=sqlite
SQLITE_PATH=/data/doc_intel.sqlite3
UPLOAD_ROOT=/data/uploads
DOCUMENT_STORAGE_BACKEND=local
```

This keeps the local demo self-contained and avoids leaking local runtime files into the repository.

## Postgres Target Profile

```powershell
docker compose --profile postgres-target up postgres-target
```

`postgres-target` exists to document the intended production database service shape. The current runtime repository adapter does not yet use Postgres, so this profile must not be described as the active production database implementation.

## Project 4 Boundary

The Docker profile runs the API, worker, local SQLite state, local storage, copilot, AgentOps, and back-office UI.

It does not make the project a production SaaS by itself. A hosted deployment still needs real auth, tenant lifecycle, Postgres-backed runtime repositories, object storage, secrets management, monitoring, backups, and HTTPS ingress.

## Smoke Check

After startup:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Expected readiness:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "storage": "ok"
  }
}
```
