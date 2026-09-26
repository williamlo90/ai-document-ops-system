[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$VaultName,
    [switch]$SetMistral,
    [switch]$SetExtractor
)

. (Join-Path $PSScriptRoot 'common.ps1')
$null = Assert-AzureSession

function Set-PromptedSecret {
    param(
        [Parameter(Mandatory)][string]$SecretName,
        [Parameter(Mandatory)][string]$Prompt
    )
    $secureValue = Read-Host $Prompt -AsSecureString
    $plainValue = [System.Net.NetworkCredential]::new('', $secureValue).Password
    try {
        if ($plainValue.Length -lt 8) {
            throw "$SecretName appears too short."
        }
        az keyvault secret set --vault-name $VaultName --name $SecretName --value $plainValue --output none --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to set Key Vault secret '$SecretName'."
        }
    }
    finally {
        $plainValue = $null
        $secureValue.Dispose()
    }
}

if (-not $SetMistral -and -not $SetExtractor) {
    throw 'Select at least one secret using -SetMistral or -SetExtractor.'
}
if ($SetMistral) {
    Set-PromptedSecret -SecretName 'mistral-api-key' -Prompt 'Mistral API key'
}
if ($SetExtractor) {
    Set-PromptedSecret -SecretName 'extractor-api-key' -Prompt 'OpenAI extractor API key'
}
Write-Host 'Requested secrets were written to Key Vault. Values were not printed.'
