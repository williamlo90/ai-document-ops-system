[CmdletBinding()]
param([Parameter(Mandatory)][string]$ResourceGroupName)

. (Join-Path $PSScriptRoot 'common.ps1')
$null = Assert-AzureSession

$exists = az group exists --name $ResourceGroupName --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Could not query the resource group.' }
if ($exists -ne 'true') {
    Write-Host "Resource group '$ResourceGroupName' does not exist."
    return
}

az resource list --resource-group $ResourceGroupName --query "sort_by([].{name:name,type:type,location:location}, &type)" --output table --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Resource inventory failed.' }
