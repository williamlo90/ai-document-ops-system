$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python is not available on PATH. Install Python 3.11+ or use Docker Desktop with scripts\start_docker.ps1."
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev-windows.txt

Write-Host "Local development environment and quality-gate tools are ready."
