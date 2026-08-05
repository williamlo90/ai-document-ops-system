[CmdletBinding()]
param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Run scripts/setup_local_venv.ps1 first."
}

$env:PYTHONPATH = Join-Path $root "backend"
$env:ENV_FILE = "C:\__codex_no_env__"
Push-Location $root
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
