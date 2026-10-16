# Phase 8 — cloud scope decision

Date: 2026-10-16. Decision: **optional new cloud deployment skipped** under the implementation
plan. The phase review is complete; a new cloud execution was not performed.
Machine-readable status: [cloud decision](cloud/report.json).

## Evidence reviewed

- [Historical Azure live validation](../../azure-live-validation.md): temporary Container Apps,
  PostgreSQL, private Blob Storage, Service Bus, Functions/Event Grid and managed-identity setup.
  The observed synthetic intake used mock providers and stopped at `needs_review`. Its record
  reports resource-group deletion and zero tagged resources at that run's teardown.
- [Phase 7](PHASE-7.md): packaged local API/worker, PostgreSQL checks, ERPNext invoice and ledger
  verification, response-loss reconciliation, restart, write rollback and SQLite/upload restore.
- [Claim contract](CLAIMS.md): full Azure-hosted invoice posting has no validated result.

## Decision and boundary

The current portfolio outcome is verified invoice processing and ERPNext sandbox posting.
Existing local/sandbox evidence proves that outcome; no unmet cloud-specific claim was selected
for this release. Another paid deployment would not add evidence required for that scope.
No new cloud resources were created and no deployment spend was incurred by this phase.
The historical teardown record was reviewed; a fresh subscription-wide resource inventory
was not performed.

The public README distinguishes local ERP results from the earlier Azure intake validation.
Cloud worker interruption, DLQ replay, restore/RPO/RTO and full ERP posting remain unverified
on Azure. The six-invoice draft timing benchmark retains its original scope.

## Completion gate

- Optional execution explicitly skipped: yes.
- Cloud and local evidence scopes separated: yes.
- New cloud resources requiring teardown: none created.
- Infrastructure retained for a separately scoped future validation: yes.

Repository organization and public README cleanup accompany this checkpoint. Original dated
release reports and runtime hash manifests remain unchanged and describe their tested revision;
the requirements relocation does not retroactively change those historical paths or image hashes.

## Repository cleanup verification

The cleanup moves Python inputs/locks into `backend/requirements/`, engineering documents into
`docs/`, the sample PDF into `examples/`, historical reconstruction records into `docs/history/`
and the design deck into `docs/assets/design/`. CI, Docker, launchers, public packaging and
provider fixtures use the new paths. All four dependency locks preserve their original package
pins and artifact hashes; historical measured reports remain unchanged.

Validation after relocation: 731 backend tests scheduled (23 optional skips), 36 frontend tests,
frontend build, Ruff, mypy (59 files), complexity budget, Linux/Windows dependency audits,
Azure IaC static validation, documentation links and the offline evaluator passed. The rebuilt
Docker image passed API/worker startup, PostgreSQL migrations, database-loss readiness and
SIGTERM checks. Seven existing frontend compiler/lint warnings remain; there are no lint errors.

The reviewed GitHub Actions update from PR 47 is integrated in this checkpoint. Bulk Python,
frontend and Node-image upgrades from PRs 49, 48 and 37 are deferred in favor of the validated
release versions. Their patches and branch history are archived outside the repository.
Automatic dependency update PR creation is disabled; security alerts remain enabled and automatic
security-fix PRs are disabled. Dependency changes are reviewed manually on `main`.
