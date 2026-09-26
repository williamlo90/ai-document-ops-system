[CmdletBinding()]
param([switch]$ConfirmSubscriptionChange)

. (Join-Path $PSScriptRoot 'common.ps1')
$null = Assert-AzureSession
if (-not $ConfirmSubscriptionChange) {
    throw 'Provider registration changes subscription state. Re-run with -ConfirmSubscriptionChange.'
}

$providers = @(
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
foreach ($provider in $providers) {
    Write-Host "Registering $provider"
    Invoke-AzChecked -Arguments @('provider', 'register', '--namespace', $provider)
}
Write-Host 'Registration was requested. Azure may take several minutes to report every provider as Registered.'
