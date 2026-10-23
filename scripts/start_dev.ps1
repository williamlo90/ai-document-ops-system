param(
    [string]$EnvFile = "",
    [string]$DataRoot = "_private_data/runtime-v1"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Local venv not found. Run scripts\setup_local_venv.ps1 first, or use scripts\start_docker.ps1."
}

$resolvedEnvFile = if ($EnvFile) {
    (Resolve-Path $EnvFile).Path
}
elseif (Test-Path (Join-Path $repoRoot "_local_docs/runtime-v1.env")) {
    (Resolve-Path (Join-Path $repoRoot "_local_docs/runtime-v1.env")).Path
}
elseif (Test-Path (Join-Path $repoRoot ".env")) {
    (Resolve-Path (Join-Path $repoRoot ".env")).Path
}
else {
    (Resolve-Path (Join-Path $repoRoot ".env.example")).Path
}
$resolvedDataRoot = if ([System.IO.Path]::IsPathRooted($DataRoot)) {
    [System.IO.Path]::GetFullPath($DataRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $DataRoot))
}
$legacyDataRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "backend/data"))
if ($resolvedDataRoot.TrimEnd('\', '/') -eq $legacyDataRoot.TrimEnd('\', '/')) {
    throw "Use a separate V1 data directory; backend/data contains preserved runtime data."
}
$uploadRoot = Join-Path $resolvedDataRoot "uploads"
$sqlitePath = Join-Path $resolvedDataRoot "doc_intel.sqlite3"
if (Test-Path -LiteralPath $sqlitePath) {
    $checkSchema = @'
import sqlite3, sys
from pathlib import Path
with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + '?mode=ro', uri=True) as connection:
    incompatible = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'ap_*'").fetchall()
if incompatible:
    raise SystemExit('V2 AP schema detected. Choose a separate V1 data directory.')
'@
    & $pythonPath -c $checkSchema $sqlitePath
    if ($LASTEXITCODE -ne 0) { throw "V1 database compatibility check failed." }
}

function Start-AppJob {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $argumentJson = ConvertTo-Json -InputObject $Arguments -Compress
    Start-Job -Name $Name -ArgumentList @(
        $repoRoot,
        $pythonPath,
        $resolvedEnvFile,
        $uploadRoot,
        $sqlitePath,
        $argumentJson
    ) -ScriptBlock {
        param($Root, $Python, $EnvFile, $UploadRoot, $SqlitePath, $ArgumentJson)

        Set-Location $Root
        $env:ENV_FILE = $EnvFile
        $env:PYTHONPATH = "backend"
        $env:UPLOAD_ROOT = $UploadRoot
        $env:SQLITE_PATH = $SqlitePath
        $env:STORAGE_BACKEND = "sqlite"
        $env:DATABASE_URL = ""
        $env:DOCUMENT_STORAGE_BACKEND = "local"
        $CommandArguments = @($ArgumentJson | ConvertFrom-Json)
        & $Python @CommandArguments
        if ($LASTEXITCODE -ne 0) {
            throw "$($CommandArguments -join ' ') exited with code $LASTEXITCODE."
        }
    }
}

$jobs = @(
    Start-AppJob -Name "invoice-review-api" -Arguments @(
        "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
    )
    Start-AppJob -Name "invoice-review-worker" -Arguments @(
        "-m", "app.worker_loop"
    )
)

Write-Host "Invoice Review API and worker are starting."
Write-Host "Open http://127.0.0.1:8000 after the readiness check passes."
Write-Host "Press Ctrl+C to stop both processes."

try {
    while (($jobs | Where-Object State -eq "Running").Count -eq $jobs.Count) {
        Receive-Job -Job $jobs
        Start-Sleep -Milliseconds 500
        $jobs = @($jobs | ForEach-Object { Get-Job -Id $_.Id })
    }

    Receive-Job -Job $jobs
    $failed = @($jobs | Where-Object State -eq "Failed")
    if ($failed.Count -gt 0) {
        $reason = ($failed | ForEach-Object { $_.ChildJobs[0].JobStateInfo.Reason.Message }) -join "; "
        throw "A development process stopped unexpectedly: $reason"
    }
}
finally {
    $jobs | Where-Object State -eq "Running" | Stop-Job
    Receive-Job -Job $jobs
    $jobs | Remove-Job -Force
}
