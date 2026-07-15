# Release Candidate Summary

Status: local portfolio release candidate.

## Included

- role-separated invoice upload and reviewer flows
- PDF viewing, structured extraction, and editable review fields
- deterministic required-field, arithmetic, supported-value, and duplicate checks
- explicit approve, reject, and correction decisions
- immutable terminal evidence and approval-gated accounting export
- processing jobs, bounded retries, dead-letter behavior, and audit records
- mock provider profile plus verified Mistral OCR and Groq extraction adapters
- 20-PDF synthetic scenario set with documented failure iterations
- local technical run and reliability evidence
- responsive desktop and mobile workflow
- Docker, CI, and public artifact packaging

## Verification Baseline

- backend suite: 370 passed, 2 skipped
- frontend suite: 11 passed
- backend Ruff check: passed
- frontend lint and production build: passed
- npm production dependency audit: no known vulnerabilities at verification time
- tracked-secret and runtime-artifact scan: passed

## Release Boundary

- invoice is the only complete document workflow
- synthetic evaluation is not customer validation or production accuracy
- local SQLite, file storage, and demo authentication are not a hosted tenancy architecture
- no measured time saving, cost saving, or business error reduction is claimed
- live ERP delivery, production monitoring, backups, and secret management remain out of scope

## Release Verdict

The artifact is suitable for a recruiter-facing local demonstration of production-shaped AI
workflow engineering. It is not a production SaaS release.
