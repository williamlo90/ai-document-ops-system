$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not available on PATH. Install Docker Desktop or use scripts\start_dev.ps1."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is installed but the Docker daemon is not running. Start Docker Desktop and retry."
}

$env:DOC_INTEL_ENV_FILE = if (Test-Path ".env") { ".env" } else { ".env.example" }
docker compose up --build
