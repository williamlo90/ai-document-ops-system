[CmdletBinding()]
param(
    [string]$FoundationOutputsPath = '',
    [string]$RuntimeOutputsPath = ''
)

. (Join-Path $PSScriptRoot 'common.ps1')
$repositoryRoot = Get-RepositoryRoot
if (-not $FoundationOutputsPath) { $FoundationOutputsPath = Join-Path $repositoryRoot '_local_docs\azure\foundation-outputs.json' }
if (-not $RuntimeOutputsPath) { $RuntimeOutputsPath = Join-Path $repositoryRoot '_local_docs\azure\runtime-outputs.json' }
$foundation = Get-FoundationOutputs -Path $FoundationOutputsPath
$runtime = Get-FoundationOutputs -Path $RuntimeOutputsPath
$null = Assert-AzureSession

$health = Invoke-WebRequest -Uri "$($runtime.apiUrl)/health" -UseBasicParsing -TimeoutSec 30
$ready = Invoke-WebRequest -Uri "$($runtime.apiUrl)/ready" -UseBasicParsing -TimeoutSec 30
if ($health.StatusCode -ne 200 -or $ready.StatusCode -ne 200) {
    throw 'API liveness or readiness did not return HTTP 200.'
}

$queue = az servicebus queue show --resource-group $foundation.resourceGroupName --namespace-name $foundation.serviceBusNamespaceName --name $foundation.serviceBusQueueName --query '{status:status,active:countDetails.activeMessageCount,deadLetter:countDetails.deadLetterMessageCount}' --output json --only-show-errors | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $queue.status -ne 'Active') {
    throw 'Service Bus queue is not active.'
}

$revision = az containerapp revision list --resource-group $foundation.resourceGroupName --name $runtime.apiName --query "[?properties.active].{name:name,health:properties.healthState,replicas:properties.replicas}" --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the active API revision.' }

Write-Host 'Live infrastructure checks passed.'
Write-Host "API: $($runtime.apiUrl)"
Write-Host "Queue active=$($queue.active) deadLetter=$($queue.deadLetter)"
Write-Host "Active revision: $revision"
