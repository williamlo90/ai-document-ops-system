# Security Remediation V1

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-001 and SEC-002 from the 15 July 2026 security baseline
- Boundary: local or hosted, mock-provider, single-workspace portfolio demo
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-001: hosted public-demo security policy | `CLOSED` | Hosted modes now require strong credentials, Secure cookies, same-origin CSRF checks, and disabled API documentation. |
| SEC-002: caller-asserted identity | `CLOSED_WITH_LIMITATION` | Role, user, and workspace come from a server-owned credential mapping and opaque session. This is sufficient for the single-workspace portfolio demo, not production IAM. |

These changes remove the two high-severity privilege and hosted-policy blockers. They do not make
the application ready for real client invoices. PDF malware assurance, retention/deletion, provider
governance, durable tenancy, and independent verification remain separate gates.

## SEC-001 Changes

- `public-demo`, `public`, `portfolio`, and production profiles now share one hosted-security predicate.
- Every hosted profile rejects missing, duplicate, known-default, or shorter-than-24-character credentials.
- Public-demo requires separate admin, uploader, and reviewer credentials.
- Public-demo remains mock-provider only.
- Hosted login cookies use `Secure`, `HttpOnly`, and `SameSite=Strict`.
- Cookie-authenticated mutations in hosted mode require a same-origin `Origin` or `Referer`.
- `/docs`, `/redoc`, and `/openapi.json` are disabled in every hosted profile.

## SEC-002 Changes

- `X-Role`, `X-User-Id`, and `X-Workspace-Id` are no longer authentication inputs.
- `APP_ADMIN_TOKEN`, `APP_UPLOADER_TOKEN`, and `APP_REVIEWER_TOKEN` map to fixed server-owned principals.
- `APP_WORKSPACE_ID` is assigned by the server for configured demo principals.
- Browser login accepts one access token and returns only an opaque, revocable HttpOnly session.
- Direct API compatibility remains available through `X-Admin-Token` for the fixed admin principal and
  `X-Access-Token` for configured role principals.
- The frontend derives its uploader or reviewer experience from the authenticated session.
- The localStorage role switch was removed; changing persona now requires signing out and using the
  other role credential.

## Executed Evidence

| Check | Result |
| --- | --- |
| Targeted security, settings, HTTP, and API tests | 49 passed |
| Full backend regression | 398 passed |
| Python lint for changed backend and test modules | Passed |
| Frontend unit tests | 13 passed |
| Frontend lint | Passed |
| Frontend production build | Passed |

The security regression set directly proves that:

1. Public-demo rejects weak or missing role credentials.
2. Public-demo disables API documentation and emits a Secure session cookie.
3. Public-demo rejects cross-origin cookie mutations.
4. Uploader login produces the server-owned uploader identity even when forged identity headers are sent.
5. Direct admin authentication ignores forged role, user, and workspace headers.
6. Uploader sessions cannot call reviewer decision APIs.
7. Workspace isolation still passes through server-issued test sessions.

## Residual Limitations

- Demo credentials are shared per role, so they do not provide individual human accountability.
- Sessions are process-local and are revoked by restart; distributed session persistence is not implemented.
- The configured demo workspace is single-workspace. Production membership and tenant provisioning are
  not implemented.
- Credential rotation is operational rather than self-service.
- An independent reviewer has not repeated the security checks.

## Release Decision

- Local synthetic demo: `PASS_WITH_LIMITATIONS`.
- Hosted mock-only demo with controlled synthetic documents: `PASS_WITH_LIMITATIONS` after independent
  configuration review.
- Hosted untrusted upload: `BLOCKED` by the remaining PDF scanning and lifecycle findings.
- Real client data or production multi-user use: `BLOCKED`.

