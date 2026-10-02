[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ImageReference,
    [Parameter(Mandatory)][string]$ClamavImageReference,
    [string]$FoundationOutputsPath = '',
    [switch]$UseRealProviders,
    [switch]$EnableProductionValidationAlerts,
    [string]$ValidationAlertEmail = '',
    [switch]$EnableProductionValidationSink,
    [switch]$EnableProductionValidationClaimJob,
    [string]$ProductionValidationRunId = '',
    [switch]$Apply,
    [switch]$ConfirmBillable
)

. (Join-Path $PSScriptRoot 'common.ps1')
$repositoryRoot = Get-RepositoryRoot
if (-not $FoundationOutputsPath) {
    $FoundationOutputsPath = Join-Path $repositoryRoot '_local_docs\azure\foundation-outputs.json'
}
$foundation = Get-FoundationOutputs -Path $FoundationOutputsPath
$null = Assert-AzureSession
Assert-ImmutableImageReference -Reference $ImageReference
Assert-ImmutableImageReference -Reference $ClamavImageReference
if ($EnableProductionValidationAlerts -and $ValidationAlertEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    throw 'ValidationAlertEmail must be supplied locally when validation alerts are enabled.'
}
if (($EnableProductionValidationSink -or $EnableProductionValidationClaimJob) -and $ProductionValidationRunId -notmatch '^[a-z0-9][a-z0-9-]{11,95}$') {
    throw 'ProductionValidationRunId is required and must use the validation run-ID format.'
}

$runtimeTemplate = Join-Path $repositoryRoot 'infra\azure\runtime.bicep'
$deploymentName = "docintel-runtime-$($foundation.sourceRevision.Substring(0, 8))"
$parameters = @(
    "namePrefix=$($foundation.namePrefix)",
    "location=$($foundation.location)",
    "sourceRevision=$($foundation.sourceRevision)",
    "expiresAt=$($foundation.expiresAt)",
    "registryName=$($foundation.registryName)",
    "storageAccountName=$($foundation.storageAccountName)",
    "documentContainerName=$($foundation.documentContainerName)",
    "serviceBusNamespaceName=$($foundation.serviceBusNamespaceName)",
    "serviceBusQueueName=$($foundation.serviceBusQueueName)",
    "keyVaultName=$($foundation.keyVaultName)",
    "containerAppsEnvironmentName=$($foundation.containerAppsEnvironmentName)",
    "apiIdentityName=$($foundation.apiIdentityName)",
    "workerIdentityName=$($foundation.workerIdentityName)",
    "migrationIdentityName=$($foundation.migrationIdentityName)",
    "validationSinkIdentityName=$($foundation.validationSinkIdentityName)",
    "validationStateContainerName=$($foundation.validationStateContainerName)",
    "logAnalyticsWorkspaceId=$($foundation.logAnalyticsWorkspaceId)",
    "imageReference=$ImageReference",
    "clamavImageReference=$ClamavImageReference",
    "useRealProviders=$($UseRealProviders.IsPresent.ToString().ToLowerInvariant())",
    "enableProductionValidationAlerts=$($EnableProductionValidationAlerts.IsPresent.ToString().ToLowerInvariant())",
    "enableProductionValidationSink=$($EnableProductionValidationSink.IsPresent.ToString().ToLowerInvariant())",
    "enableProductionValidationClaimJob=$($EnableProductionValidationClaimJob.IsPresent.ToString().ToLowerInvariant())",
    "productionValidationRunId=$ProductionValidationRunId"
)
if ($EnableProductionValidationAlerts) {
    $parameters += "validationAlertEmail=$ValidationAlertEmail"
}

if (-not $Apply) {
    Write-Host 'Running runtime what-if only. No resources will be changed.'
    Invoke-AzChecked -Arguments (@(
        'deployment', 'group', 'what-if',
        '--resource-group', $foundation.resourceGroupName,
        '--name', $deploymentName,
        '--template-file', $runtimeTemplate,
        '--result-format', 'FullResourcePayloads',
        '--parameters'
    ) + $parameters)
    return
}

Assert-ExplicitBillingApproval -Approved $ConfirmBillable.IsPresent
Invoke-AzChecked -Arguments (@(
    'deployment', 'group', 'create',
    '--resource-group', $foundation.resourceGroupName,
    '--name', $deploymentName,
    '--template-file', $runtimeTemplate,
    '--parameters'
) + $parameters)

$runtimeOutputDirectory = Join-Path $repositoryRoot '_local_docs\azure'
$runtimeOutputPath = Join-Path $runtimeOutputDirectory 'runtime-outputs.json'
az deployment group show --resource-group $foundation.resourceGroupName --name $deploymentName --query properties.outputs --output json --only-show-errors |
    Set-Content -LiteralPath $runtimeOutputPath -Encoding utf8
if ($LASTEXITCODE -ne 0) { throw 'Runtime outputs could not be saved.' }
$runtime = Get-FoundationOutputs -Path $runtimeOutputPath

Invoke-AzChecked -Arguments @(
    'functionapp', 'config', 'appsettings', 'set',
    '--resource-group', $foundation.resourceGroupName,
    '--name', $foundation.functionAppName,
    '--settings', "API_BASE_URL=$($runtime.apiUrl)",
    '--output', 'none'
)

$functionSource = Join-Path $repositoryRoot 'infra\azure\function-app'
$zipPath = Join-Path ([System.IO.Path]::GetTempPath()) "docintel-function-$([guid]::NewGuid().ToString('N')).zip"
try {
    Compress-Archive -Path (Join-Path $functionSource '*') -DestinationPath $zipPath -CompressionLevel Optimal
    Invoke-AzChecked -Arguments @(
        'functionapp', 'deployment', 'source', 'config-zip',
        '--resource-group', $foundation.resourceGroupName,
        '--name', $foundation.functionAppName,
        '--src', $zipPath,
        '--build-remote', 'true'
    )
}
finally {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
}

$eventTemplate = Join-Path $repositoryRoot 'infra\azure\event-grid.bicep'
Invoke-AzChecked -Arguments @(
    'deployment', 'group', 'create',
    '--resource-group', $foundation.resourceGroupName,
    '--name', 'docintel-event-grid',
    '--template-file', $eventTemplate,
    '--parameters',
    "location=$($foundation.location)",
    "namePrefix=$($foundation.namePrefix)",
    "storageAccountName=$($foundation.storageAccountName)",
    "functionAppName=$($foundation.functionAppName)",
    "externalDropContainerName=$($foundation.externalDropContainerName)",
    "sourceRevision=$($foundation.sourceRevision)",
    "expiresAt=$($foundation.expiresAt)"
)
Write-Host "Runtime deployed from immutable image $ImageReference"
