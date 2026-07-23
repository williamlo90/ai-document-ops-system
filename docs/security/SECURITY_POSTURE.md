# Security Posture

Last self-verification: 19 July 2026.

This is engineering evidence for a portfolio application. It is not an independent penetration
test, compliance certification, privacy opinion, or authorization to process real client invoices.

## Release Decision

| Intended use                                                                | Decision                | Remaining boundary                                                                                                     |
| --------------------------------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Loopback-only demo with synthetic data                                      | `PASS_WITH_LIMITATIONS` | Keep credentials and generated files local and ignored.                                                                |
| Controlled single-workspace hosted demo with seeded data and mock providers | `PASS_WITH_LIMITATIONS` | Deployment controls still require independent verification.                                                            |
| Hosted service accepting untrusted uploads                                  | `BLOCKED`               | A live private malware scanner, signature policy, network boundary, and EICAR evidence are not bound.                  |
| Real client data or production use                                          | `BLOCKED`               | Production identity, tenancy, provider contracts, retention, backups, TLS/DAST, and independent review are incomplete. |

## Implemented Application Controls

- server-owned sessions bind identity, role, and workspace;
- business routes enforce authentication and workspace boundaries;
- approval, correction, rejection, and export transitions are validated by the backend;
- error-level validation blocks approval;
- export uses approval checks and idempotency controls;
- private responses use `no-store` and provider endpoints use HTTPS host allowlists;
- upload size/type checks and a ClamAV adapter exist with automated tests;
- retention and deletion contracts exist at the application boundary;
- metrics use a separate credential from business routes;
- `.env`, uploads, databases, caches, and build output are excluded from Git;
- dependency, secret, workflow, and container checks are documented in the retained evidence.

## External Acceptance Gates

Before accepting real documents:

1. Deploy and verify a private malware scanner with signature updates and fail-closed behavior.
2. Approve provider retention, data location, DPA, deletion, incident response, and permitted fields.
3. Verify object-store IAM, encryption, CORS, lifecycle deletion, versions, backups, and restore.
4. Integrate production identity, user lifecycle, workspace membership, and tenant-isolation tests.
5. Verify hosted TLS, headers, CSRF, rate limits, logging, alerting, DAST, and incident procedures.
6. Obtain independent security and privacy review for the actual deployment and data class.

## Retained Evidence

- [Provider data boundary](provider-data-boundary.md)
- [Supply-chain controls](supply-chain.md)
- [Executed security evidence](security-evidence-v1.md)

The raw records above are retained for reproducibility. Superseded remediation diaries were removed
from the active documentation because this file records the current decision and unresolved gates.
