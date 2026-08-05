[CmdletBinding()]
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"

if (-not (Test-Path -LiteralPath $venv)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Unable to create .venv" }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --require-hashes -r (Join-Path $root "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
Write-Host "Environment ready: $venvPython"
