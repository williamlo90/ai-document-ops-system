[CmdletBinding()]
param(
    [string]$Location = 'southeastasia',
    [string]$SubscriptionId = ''
)

. (Join-Path $PSScriptRoot 'common.ps1')

$account = Assert-AzureSession
if ($SubscriptionId) {
    Invoke-AzChecked -Arguments @('account', 'set', '--subscription', $SubscriptionId)
    $account = Assert-AzureSession
}

Write-Host "Subscription: $($account.name)"
Write-Host 'Tenant:       authenticated (identifier redacted)'
Write-Host "Region:       $Location"

$locations = az account list-locations --query "[?name=='$Location'].name" --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or $locations -ne $Location) {
    throw "Azure region '$Location' is not available to the selected subscription."
}

$requiredProviders = @(
    'Microsoft.App',
    'Microsoft.Authorization',
    'Microsoft.ContainerRegistry',
    'Microsoft.DBforPostgreSQL',
    'Microsoft.EventGrid',
    'Microsoft.Insights',
    'Microsoft.KeyVault',
    'Microsoft.ManagedIdentity',
    'Microsoft.OperationalInsights',
    'Microsoft.ServiceBus',
    'Microsoft.Storage',
    'Microsoft.Web'
)

$missingProviders = @()
foreach ($provider in $requiredProviders) {
    $state = az provider show --namespace $provider --query registrationState --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or $state -ne 'Registered') {
        $missingProviders += $provider
    }
    Write-Host ("{0,-38} {1}" -f $provider, $state)
}

if ($missingProviders.Count -gt 0) {
    Write-Warning "Providers requiring registration: $($missingProviders -join ', ')"
    Write-Warning 'Provider registration changes subscription state and is intentionally not performed by preflight.'
}

az bicep version --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw 'Azure CLI could not run Bicep. Run az bicep install after reviewing the account setup guide.'
}

Write-Host 'Preflight completed without creating Azure resources.'
