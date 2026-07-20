# Security Remediation V3

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-005 from the 15 July 2026 security baseline
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-005: provider egress and endpoint policy | `CLOSED_WITH_GOVERNANCE_LIMITATION` | Application code enforces HTTPS, exact host allowlists, default HTTPS port, credential-free endpoint URLs, and redirect refusal. Provider contractual and account-level data handling remain externally unverified. |

## Implemented Controls

- `MISTRAL_ALLOWED_HOSTS` defaults to `api.mistral.ai`.
- `EXTRACTOR_ALLOWED_HOSTS` defaults to `api.openai.com` after the current provider migration.
- Real-provider factories and benchmark provider construction validate endpoints before creating a
  credentialed adapter.
- Configured real-provider endpoints are validated during application startup.
- URL validation rejects HTTP, userinfo, custom ports, query strings, fragments, empty allowlists,
  and hostname suffix attacks.
- Provider HTTP requests use a redirect-rejecting opener; a 3xx response becomes a sanitized,
  non-retryable provider error.
- [Provider Data Boundary](provider-data-boundary.md) records the exact application data flow and the
  acceptance evidence still required before real invoices.

## Executed Evidence

| Check | Result |
| --- | --- |
| Provider egress, transport, factory, settings, and benchmark tests | 35 passed |
| Full backend regression | 413 passed, 2 skipped |
| Ruff lint for `backend` and `scripts` | Passed |
| Repository-wide Black check | Failed on 6 pre-existing files; carried into SEC-009 remediation rather than hidden or mixed into this finding |
| Frontend unit tests | 13 passed |
| Frontend lint and production build | Passed |
| Actual ignored `.env` endpoint policy | Valid for `api.mistral.ai` and `api.openai.com`; credentials not printed |
| Runtime `/health` and `/ready` smoke | Passed |

## Residual Limitations

- No provider DPA, ZDR setting, region control, subprocessor list, or deletion evidence was inspected.
- DNS, proxy, firewall, and cloud egress policy are deployment controls outside this repository.
- The application sends the complete PDF to OCR and complete OCR text to the extractor; field-level
  redaction is not implemented.
- Real customer or client invoices remain blocked.

## Release Decision

- Synthetic local or controlled provider evaluation: `PASS_WITH_LIMITATIONS`.
- Real invoices: `BLOCKED` pending the external acceptance record above.
