# Security Remediation V2

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-003, SEC-004, and SEC-006 from the 15 July 2026 security baseline
- Boundary: local or controlled synthetic single-workspace demo; production adapter code included
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-003: signature-only upload scan | `IMPLEMENTED_UNVERIFIED` | Production requires the fail-closed ClamAV adapter. Protocol and failure behavior are test-covered; no authorized live scanner was available for this evidence run. |
| SEC-004: sensitive responses cacheable | `CLOSED` | Authenticated document, review, operations, workflow, provider, and export APIs emit `Cache-Control: no-store, private`, `Pragma: no-cache`, and `Expires: 0`. |
| SEC-006: retention and deletion undefined | `CLOSED_WITH_INFRASTRUCTURE_LIMITATION` | Admin-only dry-run and purge remove live object, parser cache, metadata, extraction, review, corrections, workflow, notifications, and document audit data. Backup and object-version lifecycle remain deployment controls. |

This closes the application-level cache and data-lifecycle gaps. It does not authorize real client
invoice processing. A production security decision still requires live ClamAV verification,
provider governance, durable tenancy, infrastructure lifecycle evidence, and independent review.

## Upload Scanning

- `MALWARE_SCANNER_BACKEND=clamav` selects a standard-library ClamAV `INSTREAM` adapter.
- `APP_ENV=production` refuses startup when scanning is disabled or the signature-only backend is
  selected.
- The scanner buffers no more than `MAX_UPLOAD_BYTES`, streams bounded chunks to ClamAV, rejects
  `FOUND`, and returns a generic `503` when verification is unavailable.
- Local and controlled synthetic demos may retain the signature guard; it is explicitly documented
  as a development control, not antivirus assurance.

## Sensitive Response Caching

Private API prefixes now receive no-store headers centrally in `SecurityHeadersMiddleware`. Static
frontend assets and health endpoints retain normal cache behavior. The policy applies to successful
and error responses, including inline PDF content.

## Retention And Deletion

- `DOCUMENT_RETENTION_DAYS` controls terminal-document eligibility; default: 90 days.
- `PARSER_CACHE_RETENTION_HOURS` controls downloaded S3 parser-cache cleanup; default: 24 hours.
- `GET /operations/retention` reports the policy and candidates for administrators.
- `POST /operations/retention/purge` defaults to dry-run and requires an explicit `dry_run=false` in
  its JSON body to delete eligible records.
- `DELETE /documents/{document_id}` performs an explicit admin-only purge using a bounded reason code
  in the JSON body, keeping free text out of URLs and access logs.
- Queued or processing documents must be cancelled before deletion to avoid a worker race.
- SQLite purge executes metadata removal and its non-PII tombstone in one database transaction.
- The tombstone stores a truncated SHA-256 document fingerprint, actor, reason, timestamp, and record
  counts; it does not retain filename, invoice values, or the original document ID.

## Executed Evidence

| Check | Result |
| --- | --- |
| Targeted scanner, cache-header, settings, storage, and retention tests | 36 passed |
| Full backend regression | 409 passed, 2 skipped |
| Python lint for `backend` and `scripts` | Passed |
| Frontend unit tests | 13 passed |
| Frontend lint | Passed |
| Frontend production build | Passed |

The targeted checks prove clean, detected, and unavailable ClamAV outcomes; production configuration
enforcement; no-store headers; idempotent local object deletion; admin-only retention dry-run;
active-document deletion blocking; and SQLite object/metadata/audit purge with a hashed tombstone.

## Residual Limitations

- No live ClamAV daemon, signature-update process, scanner health monitor, or network policy was
  available in this local evidence run.
- Public-demo remains restricted to controlled synthetic PDFs unless deployed behind the production
  scanning boundary.
- S3 object versions, provider-held copies, database backups, logs, and disaster-recovery replicas
  require separately verified lifecycle policies.
- Purge is synchronous and intended for the portfolio's bounded document volume.
- The same implementation author executed the verification.

## Release Decision

- Local synthetic demo: `PASS_WITH_LIMITATIONS`.
- Controlled mock-provider hosted demo with synthetic PDFs: `PASS_WITH_LIMITATIONS` after
  configuration review.
- Hosted untrusted uploads: `BLOCKED` until live ClamAV and infrastructure lifecycle evidence pass.
- Real client data or production multi-user use: `BLOCKED` by the remaining security and governance
  gates.
