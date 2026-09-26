[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroupName,
    [switch]$ConfirmDestroy,
    [switch]$Wait
)

. (Join-Path $PSScriptRoot 'common.ps1')
$null = Assert-AzureSession

if ($ResourceGroupName -notmatch '^rg-ai-document-[a-z0-9-]+$') {
    throw "Refusing to delete unexpected resource-group name: $ResourceGroupName"
}
if (-not $ConfirmDestroy) {
    throw 'Deletion is destructive. Re-run with -ConfirmDestroy after inventory and evidence collection.'
}

$exists = az group exists --name $ResourceGroupName --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Could not verify the deletion target.' }
if ($exists -ne 'true') {
    Write-Host "Resource group '$ResourceGroupName' is already absent."
    return
}

Write-Host "Deleting dedicated validation resource group: $ResourceGroupName"
Invoke-AzChecked -Arguments @('group', 'delete', '--name', $ResourceGroupName, '--yes', '--no-wait')
if (-not $Wait) {
    Write-Host 'Deletion accepted. Run inventory.ps1 later to confirm zero resources.'
    return
}

$deadline = (Get-Date).AddMinutes(30)
do {
    Start-Sleep -Seconds 15
    $exists = az group exists --name $ResourceGroupName --output tsv --only-show-errors
    if ($exists -eq 'false') {
        Write-Host 'Teardown verified: the validation resource group no longer exists.'
        return
    }
} while ((Get-Date) -lt $deadline)
throw 'Azure did not confirm resource-group deletion within 30 minutes.'
