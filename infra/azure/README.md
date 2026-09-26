# Azure infrastructure pack

This directory contains the account-independent Phase F infrastructure package. It compiles and is
tested locally, but it is not evidence that the application has been deployed to Azure. Live claims
remain blocked until an authenticated `what-if`, controlled deployment, workflow validation, and
teardown have all passed.

## Deployment boundary

`main.bicep` is a subscription-scope foundation deployment. It creates one dedicated, disposable
resource group containing:

- four workload-specific user-assigned identities;
- Basic Azure Container Registry with the admin account disabled;
- private Blob containers with shared-key access disabled;
- Standard Service Bus with local authentication disabled and a duplicate-aware queue;
- a cost-aware PostgreSQL Flexible Server validation SKU;
- RBAC-enabled Key Vault and generated application/database credentials;
- Log Analytics, Application Insights, and Azure Monitor diagnostics;
- a Container Apps environment;
- a Python Flex Consumption ingestion Function.

`runtime.bicep` deploys the digest-pinned API, worker, and migration job after the application image
and required Key Vault secrets exist. `event-grid.bicep` is deliberately deployed last, after the
Function code and API endpoint are ready.

The external-drop path validates Blob events in the Function, downloads the PDF using Managed
Identity, and forwards it through the application's authenticated `/documents/upload` boundary.
The application remains responsible for the PostgreSQL job record, audit trail, Blob persistence,
and Service Bus wake-up message.

## Security and cost profile

- Image parameters must be immutable `repository@sha256:digest` references. The deployment script
  rejects mutable tags.
- API, worker, migration, and ingestion use separate identities and narrowly scoped data roles.
- No secret values are emitted as Bicep outputs or committed parameter examples.
- Storage and Service Bus disable key-based/local authentication. Key Vault uses Azure RBAC.
- The API stays at one replica because sessions and rate counters remain process-local.
- The worker scales from zero; the Function uses Flex Consumption.
- The validation PostgreSQL server uses a public endpoint with the Azure-services-only firewall
  rule and TLS. This is a short-lived validation compromise, not the recommended long-running
  production network posture.
- Every taggable resource includes project, environment, source revision, and expiration metadata.
- Expiration tags are an operator signal, not an automatic hard stop. The exact resource group must
  still be deleted and verified with `destroy.ps1`.

## Safe execution order

All commands below require an Azure account except local compilation. Do not run deployment commands
until [ACCOUNT_SETUP.md](ACCOUNT_SETUP.md) has been completed.

1. `preflight.ps1` checks the selected account, region, providers, and Bicep without creating
   resources.
2. `register-providers.ps1` changes subscription state only with
   `-ConfirmSubscriptionChange`.
3. `provision.ps1` defaults to `what-if`. `-Apply -ConfirmBillable` is required to create the
   foundation.
4. `set-secrets.ps1` writes provider keys directly to Key Vault without printing them.
5. `publish-image.ps1 -ConfirmBillable` builds one clean revision, pushes it, and returns its ACR
   manifest digest.
6. `deploy-runtime.ps1` defaults to `what-if`. `-Apply -ConfirmBillable` deploys the runtime,
   publishes the Function, and then enables Event Grid.
7. `migrate.ps1 -ConfirmBillable` runs the manual migration job and waits for success.
8. `validate-live.ps1` checks health, readiness, queue status, and the active revision.
9. `collect-evidence.ps1` saves a sanitized local record under ignored `_local_docs/azure/`.
10. `inventory.ps1` lists the exact teardown target.
11. `destroy.ps1 -ConfirmDestroy -Wait` deletes the dedicated validation resource group and proves
    that it is absent.

The scripts never create resources merely because Azure CLI is installed or a user has logged in.
Billable mutations require explicit switches.

## Local validation

The CI job uses Bicep `v0.45.15`, verifies the official binary checksum, compiles all three entry
points, and inspects the generated ARM templates:

```powershell
python scripts/validate_azure_iac.py --compiled-dir <compiled-json-directory>
```

The validator checks encryption/authentication controls, immutable image contracts, secret-free
outputs, role boundaries, resource tags, and guarded teardown behavior.
