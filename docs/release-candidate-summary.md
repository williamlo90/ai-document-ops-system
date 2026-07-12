# Release Candidate Summary - AI Document Operations System

Status: demo-ready local-first release candidate.

## What This Release Is

AI Document Operations System is an invoice-first document operations app with:

- secure local operator session
- invoice intake, extraction, validation, and source evidence review
- role-focused uploader and reviewer flows
- review queue and exception handling
- bounded planning for document work
- human Approval Decision flow for risky execution
- controlled execution after approval
- durable workflow History and audit evidence
- technical evidence APIs and pages for System Reliability, Reliability Checks, Test Scenarios, and Run Traces

## Verification

- Backend full suite: 367 tests OK, 2 skipped
- Frontend tests: 8 tests OK
- Frontend lint: passed
- Frontend production build: passed
- Docker compose config: passed
- Public artifact tests: 16 tests OK
- Public artifact packaging script: passed to a temporary output folder

Focused Ruff lint and format checks passed for the latest backend hardening changes.

## Honest Boundaries

- Invoice is the only complete extraction, validation, planning, and execution schema.
- Generic `/documents/*` contracts are additive; invoice compatibility aliases remain intentionally supported.
- A second executable document workflow is intentionally deferred.
- This is a local-first portfolio system, not hosted production SaaS.
- Real customer deployment, tenancy, billing, backups, production monitoring, and live-provider credentials are out of scope.

## Recommended Release Tag

```text
v0.4.0-rc1
```
