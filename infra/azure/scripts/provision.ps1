[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SubscriptionId,
    [string]$Location = 'southeastasia',
    [string]$ResourceGroupName = 'rg-ai-document-validation-sea',
    [string]$EnvironmentName = 'validation',
    [string]$SourceRevision = '',
    [datetime]$ExpiresAt = (Get-Date).ToUniversalTime().AddHours(4),
    [switch]$Apply,
    [switch]$ConfirmBillable
)

. (Join-Path $PSScriptRoot 'common.ps1')
$repositoryRoot = Get-RepositoryRoot
$template = Join-Path $repositoryRoot 'infra\azure\main.bicep'
$outputDirectory = Join-Path $repositoryRoot '_local_docs\azure'
$outputPath = Join-Path $outputDirectory 'foundation-outputs.json'

$account = Assert-AzureSession
Invoke-AzChecked -Arguments @('account', 'set', '--subscription', $SubscriptionId)
if (-not $SourceRevision) {
    $SourceRevision = (git -C $repositoryRoot rev-parse HEAD).Trim()
}
if ($SourceRevision -notmatch '^[a-f0-9]{40}$') {
    throw 'SourceRevision must be a full 40-character Git commit SHA.'
}

$deploymentName = "docintel-foundation-$($SourceRevision.Substring(0, 8))"
$parameters = @(
    "environmentName=$EnvironmentName",
    "location=$Location",
    "resourceGroupName=$ResourceGroupName",
    "sourceRevision=$SourceRevision",
    "expiresAt=$($ExpiresAt.ToString('o'))"
)

if (-not $Apply) {
    Write-Host 'Running subscription what-if only. No resources will be created.'
    Invoke-AzChecked -Arguments (@(
        'deployment', 'sub', 'what-if',
        '--name', $deploymentName,
        '--location', $Location,
        '--template-file', $template,
        '--result-format', 'FullResourcePayloads',
        '--parameters'
    ) + $parameters)
    return
}

Assert-ExplicitBillingApproval -Approved $ConfirmBillable.IsPresent
Invoke-AzChecked -Arguments (@(
    'deployment', 'sub', 'create',
    '--name', $deploymentName,
    '--location', $Location,
    '--template-file', $template,
    '--parameters'
) + $parameters)

New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
az deployment sub show --name $deploymentName --query properties.outputs --output json --only-show-errors |
    Set-Content -LiteralPath $outputPath -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    throw 'Foundation deployed, but its non-secret outputs could not be saved locally.'
}
Write-Host "Foundation outputs saved to ignored local file: $outputPath"
