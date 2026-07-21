# Release Candidate Summary

Status: local portfolio release candidate.

## Included

- role-separated invoice upload and reviewer flows
- PDF viewing, structured extraction, and editable review fields
- deterministic required-field, arithmetic, supported-value, and duplicate checks
- explicit approve, reject, and correction decisions
- immutable terminal evidence and approval-gated accounting export
- processing jobs, bounded retries, dead-letter behavior, and audit records
- mock provider profile plus verified Mistral OCR and OpenAI extraction adapters
- 20-PDF synthetic scenario set with documented failure iterations
- private external licensed synthetic FATURA pack with diagnostic and checksum-sealed holdout splits
- preserved V1 provider-availability failure plus a non-overlapping V2 sealed holdout with
  10 / 10 provider success, 98.75% field accuracy, and one documented hallucinated due date
- reviewer correction feedback with original AI snapshot, before/after diffs, reason lineage, and
  privacy-filtered aggregate evidence
- local technical run and reliability evidence
- eight client-facing product pages with a four-viewport screenshot matrix
- a captioned recruiter demo covering review, correction, approval, export, evaluation, and system evidence
- Docker, CI, and public artifact packaging

## Verification Baseline

- backend suite: 453 passed, 2 skipped
- frontend suite: 13 passed
- backend Ruff check: passed
- frontend lint and production build: passed
- Python and npm dependency audits: no known vulnerabilities at verification time
- tracked-secret and runtime-artifact scan: passed

## Release Boundary

- invoice is the only complete document workflow
- synthetic and licensed-synthetic evaluation are not customer validation or production accuracy
- V1 failed provider availability; V2 passed its bounded gates, but neither establishes a production
  provider SLA or market-wide accuracy
- local SQLite, file storage, and demo authentication are not a hosted tenancy architecture
- no measured time saving, cost saving, or business error reduction is claimed
- live ERP delivery, production monitoring, backups, and secret management remain out of scope
- Settings is intentionally absent until it has an approved design and an audited persisted
  server contract; no placeholder route ships in this candidate

## Release Verdict

The artifact is suitable for a recruiter-facing local demonstration of production-shaped AI
workflow engineering. It is not a production SaaS release.
