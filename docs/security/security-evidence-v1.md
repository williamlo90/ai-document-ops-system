# Security Evidence And Traceability V1

- Evidence cutoff: 15 July 2026, 13:03:23 UTC+07:00
- Repository: `main` at `b519f4150a01483b6112aa94416d69cf3733069a` plus inspected working-tree changes
- Mode: `SELF_VERIFICATION`
- Current decision: [Security Posture](SECURITY_POSTURE.md)

This file preserves the original 15 July baseline evidence. Findings and checks below are historical;
use the linked security posture for the current decision and residual acceptance gates.

## Candidate Binding

The worktree already contained modifications to portfolio documentation, lifecycle cleanup code, and
public-artifact handling before this audit. Those changes were inspected and preserved. The audit did
not treat the candidate as a clean release commit and did not modify application code.

## Baseline Executed Evidence

| Claim                                                   | State                | Check                                                                                                                         | Observed result                                                                                                |
| ------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Current route inventory is known                        | `VERIFIED`           | Python AST inventory of FastAPI route decorators and security dependencies                                                    | Business APIs were dependency-protected; health, readiness, auth, redirects, and internal metrics were public. |
| Core security behavior remains green                    | `VERIFIED`           | `python -m unittest` over security, HTTP security, storage, API, intake, review/export, integration, and CSV-security modules | 84 tests passed.                                                                                               |
| Full backend regression remains green                   | `VERIFIED`           | Repository backend test command                                                                                               | 393 tests passed in 21.251 seconds.                                                                            |
| Frontend quality gate remains green                     | `VERIFIED`           | `npm run lint`, `npm run test`, and `npm run build`                                                                           | Lint passed, 13 tests passed, and the production build completed.                                              |
| Hosted-mode negative behavior is reproduced             | `VERIFIED`           | Isolated TestClient script for production and public-demo profiles                                                            | Production rejected weak token; public-demo accepted it and lacked Secure-cookie, CSRF, and docs hardening.    |
| Upload scanner limitation is reproduced                 | `VERIFIED`           | Isolated upload of malformed signature-only PDF marker                                                                        | Upload returned success; scanner is not a real PDF or malware validator.                                       |
| Sensitive PDF cache policy is absent                    | `VERIFIED`           | Fetch uploaded document content through authenticated TestClient                                                              | Response did not include `Cache-Control: no-store`.                                                            |
| Identity headers are caller-asserted                    | `VERIFIED`           | Direct `verify_admin_token` invocation with arbitrary workspace/user/role                                                     | Shared token produced the asserted reviewer context.                                                           |
| Current frontend dependency graph has no known advisory | `VERIFIED`           | `npm audit --json`                                                                                                            | 0 known vulnerabilities in the current lockfile.                                                               |
| Current Python environment has no runtime advisory      | `PARTIALLY_VERIFIED` | Temporary `pip-audit --path .venv/Lib/site-packages --format json`                                                            | Runtime packages had no reported advisory; development Black 24.10.0 had two advisories.                       |
| Static Python scan completed                            | `PARTIALLY_VERIFIED` | Temporary `bandit -r backend scripts -x backend/app/tests -f json`                                                            | 0 high, 5 medium, and 9 low analyzer findings; medium results were configurable `urlopen` scheme checks.       |
| `.env` is excluded                                      | `VERIFIED`           | `git check-ignore -v .env` and `git ls-files --error-unmatch .env`                                                            | `.env` is ignored and not tracked.                                                                             |
| No obvious tracked credential was found                 | `PARTIALLY_VERIFIED` | Bounded redacted patterns against tracked tip and matching history commits                                                    | Only fixtures/placeholders were found; dedicated secret scanner was unavailable.                               |
| Existing frontend avoids production raw HTML insertion  | `VERIFIED`           | Source search for `dangerouslySetInnerHTML`, `innerHTML`, `eval`, and persistent token use                                    | No production raw HTML/eval sink found; admin credential is not written to browser storage.                    |

## Requirements Traceability

| Requirement or claim                                         | Control evidence                                                     | Finding or residual risk                                                |
| ------------------------------------------------------------ | -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| PRD: preserve role and workspace boundaries                  | Service role checks and workspace-negative tests                     | SEC-002: authentication can mint caller-asserted identity scope         |
| PRD: security headers, rate limiting, CSRF, protected routes | `test_http_security`, route inventory                                | SEC-001 and SEC-010 for public-demo and metrics                         |
| PRD: repository excludes credentials and uploads             | `.gitignore`, ignored `.env`, public-artifact tests                  | Dedicated secret scanning remains not run                               |
| Architecture: private document storage                       | generated storage keys, root traversal checks, auth content endpoint | SEC-004 and SEC-006 for cache and lifecycle                             |
| Architecture: approval-gated export                          | review/export and integration tests                                  | SEC-007 for ambiguous outbound replay                                   |
| Portfolio claim: evidence-bound extraction                   | exact-source grounding and deterministic validation tests            | SEC-008: adversarial prompt-injection evidence missing                  |
| Provider-backed workflow                                     | Mistral and OpenAI adapters plus prior provider evidence             | SEC-005: egress policy, HTTPS allowlist, ZDR, region, and DPA not bound |

## Checks Not Run In The Baseline

| Check                                                   | State                   | Reason and required next evidence                                                         |
| ------------------------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------- |
| Independent security review                             | `NOT_RUN`               | Builder and verifier are the same; repeat after remediation with an independent reviewer. |
| Gitleaks/detect-secrets full history scan               | `NOT_RUN_LOCAL`         | Tools were unavailable; run in CI or install a pinned scanner.                            |
| Container image and OS package scan                     | `NOT_RUN_LOCAL`         | Trivy/Docker Scout was unavailable; scan the immutable release image.                     |
| Hosted DAST and TLS/HSTS verification                   | `NOT_RUN`               | No authorized hosted candidate was bound.                                                 |
| R2/S3 IAM, encryption, CORS, and lifecycle verification | `CONFIGURED_UNVERIFIED` | No cloud account/configuration was inspected.                                             |
| Real antivirus or PDF sanitization                      | `NOT_RUN`               | No scanner service is integrated.                                                         |
| Real-provider security call                             | `NOT_RUN`               | Avoided sending data or spending quota during a read-only audit.                          |
| Provider contract/DPA and legal privacy review          | `NOT_RUN`               | Requires owner and qualified legal/privacy decision.                                      |
| Retention/deletion and backup restore                   | `NOT_RUN`               | Capability and acceptance contract are not implemented.                                   |
| Audit tamper evidence                                   | `NOT_RUN`               | Current repositories do not claim or implement cryptographic tamper evidence.             |

## Resource And Safety Record

- No production system, real customer data, or paid provider was accessed.
- Test uploads used temporary directories and synthetic marker content.
- Security tools were installed under the OS temporary directory, not into the project environment.
- No application code, credentials, private invoices, database, or existing user modification was changed.
- Network access was limited to dependency advisory services and official provider and formatter documentation.

## Baseline Recommendation

This recommendation has been superseded by the
[Security Posture](SECURITY_POSTURE.md). The original two high
application findings were remediated for the controlled single-workspace demo boundary; untrusted
uploads and real-data use remain blocked by the external acceptance gates in the completion audit.
