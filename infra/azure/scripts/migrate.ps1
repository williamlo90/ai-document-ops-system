[CmdletBinding()]
param(
    [string]$FoundationOutputsPath = '',
    [string]$RuntimeOutputsPath = '',
    [switch]$ConfirmBillable
)

. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ExplicitBillingApproval -Approved $ConfirmBillable.IsPresent
$repositoryRoot = Get-RepositoryRoot
if (-not $FoundationOutputsPath) {
    $FoundationOutputsPath = Join-Path $repositoryRoot '_local_docs\azure\foundation-outputs.json'
}
if (-not $RuntimeOutputsPath) {
    $RuntimeOutputsPath = Join-Path $repositoryRoot '_local_docs\azure\runtime-outputs.json'
}
$foundation = Get-FoundationOutputs -Path $FoundationOutputsPath
$runtime = Get-FoundationOutputs -Path $RuntimeOutputsPath
$null = Assert-AzureSession

$executionName = az containerapp job start --resource-group $foundation.resourceGroupName --name $runtime.migrationJobName --query name --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or -not $executionName) {
    throw 'Migration job could not be started.'
}
Write-Host "Migration execution: $executionName"

$deadline = (Get-Date).AddMinutes(20)
do {
    Start-Sleep -Seconds 10
    $status = az containerapp job execution show --resource-group $foundation.resourceGroupName --name $runtime.migrationJobName --job-execution-name $executionName --query properties.status --output tsv --only-show-errors
    Write-Host "Migration status: $status"
    if ($status -eq 'Succeeded') { return }
    if ($status -in @('Failed', 'Stopped', 'Degraded')) {
        throw "Migration job ended with status: $status"
    }
} while ((Get-Date) -lt $deadline)
throw 'Migration job did not finish within 20 minutes.'
