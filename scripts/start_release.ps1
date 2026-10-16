param([switch]$Seed, [switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:RELEASE_PARSER_PROVIDER = 'mock'
$env:RELEASE_EXTRACTOR_PROVIDER = 'mock'
$env:RELEASE_ACCOUNTING_PROVIDER = 'csv_download'
$env:RELEASE_POSTING_ENABLED = 'false'
$env:RELEASE_DROP_SUBMIT_ONCE = 'false'
$demoPort = if ($env:DOC_INTEL_PORT) { $env:DOC_INTEL_PORT } else { '8000' }
$compose = @('compose', '-p', 'invoice-review-release', '-f', 'docker-compose.yml', '-f', 'docker-compose.release.yml')
if (-not $SkipBuild) {
    $revision = (git rev-parse HEAD).Trim()
    if (git status --porcelain -- Dockerfile .dockerignore requirements.txt backend frontend examples scripts/phase7_sandbox_bridge.py) {
        $revision = "$revision-dirty"
    }
    $created = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    & docker @compose build --build-arg "SOURCE_REVISION=$revision" --build-arg "BUILD_CREATED_AT=$created" api
    if ($LASTEXITCODE -ne 0) { throw 'Release image build failed.' }
}
& docker @compose up -d --no-build --wait api worker
if ($LASTEXITCODE -ne 0) { throw 'Release services did not become ready.' }
if ($Seed) {
    & .venv/Scripts/python.exe scripts/phase7_demo.py --base "http://127.0.0.1:$demoPort"
    if ($LASTEXITCODE -ne 0) { throw 'Seeded AP demonstration failed.' }
}
Write-Output "Open http://127.0.0.1:$demoPort. Local role tokens: release-reviewer, release-approver, release-admin."
Write-Output 'Stop with: docker compose -p invoice-review-release -f docker-compose.yml -f docker-compose.release.yml stop'
