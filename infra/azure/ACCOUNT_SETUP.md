# Azure account setup — perform only after local infrastructure validation

No Azure account is required to write, compile, or test this infrastructure. Use these steps only
when you are ready to inspect an authenticated `what-if` and potentially begin the short billable
validation window.

## 1. Determine whether an account and subscription already exist

1. Open [Azure Portal](https://portal.azure.com/) and sign in with the Microsoft account you intend
   to own the portfolio resources.
2. Search for **Subscriptions**.
3. If an active subscription appears, record its display name and subscription ID privately.
4. If no active subscription exists, review the current terms on the
   [Azure free account page](https://azure.microsoft.com/free/) before adding a payment method.
5. Enable MFA and confirm account recovery information. The subscription, billing method, MFA, and
   recovery controls remain owner responsibilities.

Do not paste a subscription ID, tenant ID, invoice, payment detail, recovery code, or API key into
Git, screenshots, or chat.

## 2. Establish cost visibility before provisioning

In the portal, open **Cost Management + Billing**, select the subscription, and create a small
monthly budget with actual and forecast alerts sent to your email. A budget is an alert, not a hard
spending cap. Microsoft notes that a new subscription can take up to 48 hours before all Cost
Management features are available, and cost data/alerts are delayed.

Official guidance: [Create and manage Azure budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

## 3. Install Azure CLI on Windows

Open a normal PowerShell window and run:

```powershell
winget install --exact --id Microsoft.AzureCLI
```

Close and reopen the terminal, then verify:

```powershell
az version
az bicep install
az bicep version
```

Official guidance: [Install Azure CLI on Windows](https://learn.microsoft.com/cli/azure/install-azure-cli-windows).

## 4. Sign in interactively and select the subscription

```powershell
az login
az account list --output table
az account set --subscription "<subscription-id>"
az account show --output table
```

`az login` opens a Microsoft browser sign-in and supports MFA. Confirm that `az account show`
displays the intended subscription before proceeding. Official guidance:
[Azure CLI authentication](https://learn.microsoft.com/cli/azure/authenticate-azure-cli).

## 5. Run read-only project preflight

From the repository root:

```powershell
.\infra\azure\scripts\preflight.ps1 -Location southeastasia
```

The preflight does not register providers or create resources. If providers are missing, review the
list before running:

```powershell
.\infra\azure\scripts\register-providers.ps1 -ConfirmSubscriptionChange
```

Provider registration changes subscription state but does not itself deploy the application.

## 6. Stop at authenticated what-if

The first infrastructure preview is non-deploying because `-Apply` is omitted:

```powershell
.\infra\azure\scripts\provision.ps1 `
  -SubscriptionId "<subscription-id>" `
  -Location southeastasia
```

Review resource names, types, region, and expected changes. Do not add `-Apply` or
`-ConfirmBillable` until the what-if and current subscription-aware price estimate have been
reviewed. The controlled live procedure is documented separately in the project runbook.
