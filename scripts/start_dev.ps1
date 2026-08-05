$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    throw "Local venv not found. Run scripts\setup_local_venv.ps1 first, or use scripts\start_docker.ps1."
}

$envFile = if (Test-Path (Join-Path $repoRoot ".env")) {
    (Resolve-Path (Join-Path $repoRoot ".env")).Path
}
else {
    (Resolve-Path (Join-Path $repoRoot ".env.example")).Path
}
$uploadRoot = Join-Path $repoRoot "backend\data\uploads"
$sqlitePath = Join-Path $repoRoot "backend\data\doc_intel.sqlite3"

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
        $envFile,
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
