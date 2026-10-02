[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$JobId,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9-]{11,95}$')][string]$RunId,
    [string]$FoundationOutputsPath = '',
    [string]$RuntimeOutputsPath = '',
    [switch]$ConfirmLeaseAbandonment,
    [switch]$ConfirmBillable
)

. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ExplicitBillingApproval -Approved $ConfirmBillable.IsPresent
if (-not $ConfirmLeaseAbandonment) {
    throw 'Pass -ConfirmLeaseAbandonment to acknowledge the intentional stale lease.'
}
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
if (-not $runtime.validationClaimJobName) {
    throw 'The validation claim job was not deployed.'
}

$executionName = az containerapp job start `
    --resource-group $foundation.resourceGroupName `
    --name $runtime.validationClaimJobName `
    --container-name 'claim-and-exit' `
    --args '--job-id' $JobId '--run-id' $RunId '--confirm-lease-abandonment' `
    --query name --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or -not $executionName) {
    throw 'The guarded claim-and-exit job could not be started.'
}
Write-Host "Claim-and-exit execution: $executionName"

$deadline = (Get-Date).AddMinutes(5)
do {
    Start-Sleep -Seconds 5
    $status = az containerapp job execution show `
        --resource-group $foundation.resourceGroupName `
        --name $runtime.validationClaimJobName `
        --job-execution-name $executionName `
        --query properties.status --output tsv --only-show-errors
    Write-Host "Claim-and-exit status: $status"
    if ($status -eq 'Succeeded') { return }
    if ($status -in @('Failed', 'Stopped', 'Degraded')) {
        throw "Claim-and-exit ended with status: $status"
    }
} while ((Get-Date) -lt $deadline)
throw 'Claim-and-exit did not finish within 5 minutes.'
