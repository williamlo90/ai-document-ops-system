# Azure Container Apps runtime contract

These YAML files preserve the Phase E runtime contract for the API, worker, and manual migration
job. They deliberately contain placeholders and are not deployment evidence. The deployable,
parameterized Phase F implementation is now in the parent `infra/azure/` directory.

All three workloads use the same digest-pinned image. A user-assigned managed identity pulls from
ACR and authenticates to Blob Storage, Service Bus, and Key Vault. Only values that are inherently
secret are exposed through Key Vault-backed Container Apps secrets. The API uses separate liveness
and readiness probes. The worker scales from zero on Service Bus backlog and relies on process
liveness plus database polling for recovery. The migration job is manual, serialized inside
PostgreSQL with an advisory lock, and reads `DATABASE_URL` from its environment rather than argv.

Do not replace `<IMAGE_DIGEST>` with a mutable tag. The release workflow must use the exact digest
produced from a clean Git commit.
