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

$resources = az resource list --resource-group $foundation.resourceGroupName --query "[].{name:name,type:type,location:location}" --output json --only-show-errors | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not collect the sanitized resource inventory.' }
$api = az containerapp show --resource-group $foundation.resourceGroupName --name $runtime.apiName --query '{name:name,latestReadyRevision:properties.latestReadyRevisionName,provisioningState:properties.provisioningState,runningStatus:properties.runningStatus}' --output json --only-show-errors | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not collect API status.' }
$queue = az servicebus queue show --resource-group $foundation.resourceGroupName --namespace-name $foundation.serviceBusNamespaceName --name $foundation.serviceBusQueueName --query '{status:status,activeMessages:countDetails.activeMessageCount,deadLetterMessages:countDetails.deadLetterMessageCount}' --output json --only-show-errors | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Could not collect queue status.' }

$evidence = [ordered]@{
    collectedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    sourceRevision = $foundation.sourceRevision
    location = $foundation.location
    resourceGroupName = $foundation.resourceGroupName
    api = $api
    queue = $queue
    resources = $resources
}
$outputDirectory = Join-Path $repositoryRoot '_local_docs\azure\evidence'
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$outputPath = Join-Path $outputDirectory "evidence-$((Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')).json"
$evidence | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outputPath -Encoding utf8
Write-Host "Sanitized evidence saved locally: $outputPath"
