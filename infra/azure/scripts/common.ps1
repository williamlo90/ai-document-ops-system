Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepositoryRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
}

function Assert-CommandAvailable {
    param([Parameter(Mandatory)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not installed or not on PATH."
    }
}

function Assert-AzureSession {
    Assert-CommandAvailable -Name 'az'
    $account = az account show --only-show-errors --output json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $account) {
        throw 'No active Azure CLI session. Run az login, then select a subscription.'
    }
    return ($account | ConvertFrom-Json)
}

function Assert-ExplicitBillingApproval {
    param([Parameter(Mandatory)][bool]$Approved)
    if (-not $Approved) {
        throw 'This command can create or update billable Azure resources. Re-run with -ConfirmBillable after reviewing what-if.'
    }
}

function Assert-ImmutableImageReference {
    param([Parameter(Mandatory)][string]$Reference)
    if ($Reference -notmatch '@sha256:[a-f0-9]{64}$') {
        throw "Image reference must end in @sha256:<64 lowercase hex characters>: $Reference"
    }
}

function Get-FoundationOutputs {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Foundation outputs were not found: $Path"
    }
    $raw = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    $result = @{}
    foreach ($property in $raw.PSObject.Properties) {
        $result[$property.Name] = $property.Value.value
    }
    return $result
}

function Invoke-AzChecked {
    param([Parameter(Mandatory)][string[]]$Arguments)
    & az @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI command failed: az $($Arguments -join ' ')"
    }
}
