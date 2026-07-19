# Security Hardening Completion Audit

- Verification date: 19 July 2026
- Candidate: `main` after the SEC-001 through SEC-010 remediation series and the completion slice containing this report
- Mode: `SELF_VERIFICATION`
- Intended release boundary: local synthetic demo and controlled single-workspace hosted demo with seeded synthetic data and mock providers
- Assessor: Codex, which also implemented parts of the remediation

This is engineering evidence, not an independent penetration test, privacy opinion, compliance
certification, or authorization to process real client invoices.

## Decision

| Use | Decision | Basis |
| --- | --- | --- |
| Loopback-only demo with synthetic data | `PASS_WITH_LIMITATIONS` | Application controls and release gates executed successfully. |
| Controlled hosted demo with seeded synthetic data, mock providers, private metrics ingress, and no public upload | `PASS_WITH_LIMITATIONS` | Hosted policy, server-owned roles, dedicated metrics auth, immutable supply chain, and deterministic workflow controls are implemented. Deployment controls still require independent verification. |
| Hosted service accepting untrusted uploads | `BLOCKED` | The ClamAV adapter exists and is test-covered, but an authorized live scanner, signature-update policy, network boundary, and live EICAR result are not bound. |
| Real client data or production use | `BLOCKED` | Provider contracts, infrastructure lifecycle, production identity and tenancy, backup deletion, TLS/DAST, and independent review are not established. |

All ten application findings in the 15 July baseline have locally actionable remediation. This means
the repository no longer has a known open application-code finding from that baseline. It does not
convert deployment, legal, provider, or independent-verification work into completed evidence.

## Finding Closure

| Finding | Application status | Residual boundary |
| --- | --- | --- |
| SEC-001 hosted security profile | Remediated | Verify headers, TLS, CSRF, and docs exposure on the hosted candidate. |
| SEC-002 caller-owned identity | Remediated for the single-workspace demo | Production IAM, individual lifecycle, and multi-tenant authorization remain out of scope. |
| SEC-003 untrusted PDF protection | Adapter implemented and test-covered | Live ClamAV deployment and sanitization policy remain external gates. |
| SEC-004 sensitive caching | Remediated | Verify browser, proxy, CDN, and object-store behavior in deployment. |
| SEC-005 provider egress | Remediated in code | ZDR, retention, region, DPA, deletion, and permitted-data decisions remain external. |
| SEC-006 retention and deletion | Remediated in the application | Object versions, backups, and managed-store lifecycle need hosted evidence. |
| SEC-007 outbound idempotency | Remediated | External accounting systems must honor the same delivery key contract. |
| SEC-008 adversarial invoice instructions | Remediated with bounded detection | Detection is heuristic; deterministic validation and human approval remain mandatory. |
| SEC-009 supply chain | Remediated | Advisory databases are point-in-time and require ongoing updates. |
| SEC-010 internal metrics | Remediated in the application | Keep metrics outside public ingress and rotate its dedicated credential. |

## Executed Evidence

| Gate | Result |
| --- | --- |
| Backend regression | `425 passed`, `2 skipped` |
| Python formatting and lint | Ruff format check and Ruff check passed across `backend`, `scripts`, and `run_tests.py` |
| Python dependency audit | `pip-audit` reported no known runtime vulnerability |
| Frontend unit suite | `13 passed` |
| Frontend browser suite | `22 passed`, `8` capture-only tests skipped across desktop, tablet, and mobile |
| Frontend lint and production build | Passed |
| Frontend dependency audit | npm reported `0` vulnerabilities |
| Workflow validation | `actionlint` passed |
| Secret scanning | Digest-pinned Gitleaks scanned full Git history; no leak remained after one exact local-demo placeholder was narrowly allowlisted |
| Container build | Digest-pinned Node and Python bases built successfully as a non-root runtime image |
| Container runtime smoke | `/health` and `/ready` returned `200`; metrics required its dedicated token and returned private `no-store`; the metrics token was rejected by a business route |
| Container vulnerability scan | Digest-pinned Trivy 0.72.0 reported `0` HIGH/CRITICAL findings for OS and Python packages with `--ignore-unfixed` |
| Static configuration inventory | GitHub Actions and source-controlled container bases use immutable revisions; frontend direct dependencies are exact; Python locks are hash-verified |
| Credential hygiene | `.env` is ignored and untracked; only `.env.example` is versioned |

The E2E completion run also caught stale tests that selected authority through `localStorage`. The tests
now receive uploader or reviewer role from the mocked server session, matching the remediated identity
boundary.

## Public Route Decision

The intentionally unauthenticated application endpoints are `/health`, `/ready`, session creation,
legacy UI redirects, and static frontend assets. Business APIs require a server-derived session or
access-token principal. `/internal/metrics` requires the separate `X-Metrics-Token`; business
credentials and the metrics credential are intentionally not interchangeable.

## External Acceptance Gates

The following cannot be closed by more local code:

1. Deploy ClamAV or an approved equivalent on a private network path, define signature updates and
   fail-closed behavior, and retain a successful live EICAR test.
2. Approve provider ZDR/retention, data location, DPA, incident response, deletion, quota, and allowed
   invoice data before enabling real providers for real documents.
3. Verify object-store IAM, encryption, CORS, presigned URL behavior, lifecycle deletion, object
   versions, backups, and restore/deletion evidence in the selected cloud account.
4. Bind a production identity provider, user lifecycle, workspace membership, and tenant-isolation
   tests before making multi-user or multi-tenant claims.
5. Deploy the exact scanned image digest behind TLS, keep metrics on private ingress, rotate secrets,
   and run authorized DAST and configuration review.
6. Have a reviewer who did not implement these controls repeat the high-risk checks.

Until those criteria are evidenced, the defensible statement is:

> The repository has a self-verified, production-shaped security boundary for a controlled synthetic
> demo. It is not certified or approved for untrusted public uploads or real client data.
