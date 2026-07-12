$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Local venv not found. Run scripts\setup_local_venv.ps1 first, or use scripts\start_docker.ps1."
}

$env:ENV_FILE = if (Test-Path ".env") { ".env" } else { ".env.example" }
$env:PYTHONPATH = "backend"
$env:UPLOAD_ROOT = "backend/data/uploads"
$env:SQLITE_PATH = "backend/data/doc_intel.sqlite3"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
