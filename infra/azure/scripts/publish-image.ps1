[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ResourceGroupName,
    [Parameter(Mandatory)][string]$RegistryName,
    [string]$Repository = 'ai-document-ops',
    [string]$SourceRevision = '',
    [switch]$ConfirmBillable
)

. (Join-Path $PSScriptRoot 'common.ps1')
Assert-ExplicitBillingApproval -Approved $ConfirmBillable.IsPresent
$null = Assert-AzureSession
Assert-CommandAvailable -Name 'docker'

$repositoryRoot = Get-RepositoryRoot
if (-not $SourceRevision) {
    $SourceRevision = (git -C $repositoryRoot rev-parse HEAD).Trim()
}
if ($SourceRevision -notmatch '^[a-f0-9]{40}$') {
    throw 'SourceRevision must be a full 40-character Git commit SHA.'
}

$localTag = "docintel:$SourceRevision"
& (Join-Path $repositoryRoot '.venv\Scripts\python.exe') (Join-Path $repositoryRoot 'scripts\build_release_image.py') --tag $localTag
if ($LASTEXITCODE -ne 0) {
    throw 'Release image build failed.'
}

Invoke-AzChecked -Arguments @('acr', 'login', '--name', $RegistryName)
$loginServer = az acr show --name $RegistryName --resource-group $ResourceGroupName --query loginServer --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or -not $loginServer) {
    throw 'Could not resolve the ACR login server.'
}

$remoteTag = "$loginServer/$Repository`:$SourceRevision"
docker tag $localTag $remoteTag
if ($LASTEXITCODE -ne 0) { throw 'Docker tag failed.' }
docker push $remoteTag
if ($LASTEXITCODE -ne 0) { throw 'Docker push failed.' }

$digest = az acr repository show --name $RegistryName --image "$Repository`:$SourceRevision" --query digest --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or $digest -notmatch '^sha256:[a-f0-9]{64}$') {
    throw 'ACR did not return a valid immutable manifest digest.'
}
$immutableReference = "$loginServer/$Repository@$digest"
Write-Host "Immutable image: $immutableReference"
Write-Output $immutableReference
