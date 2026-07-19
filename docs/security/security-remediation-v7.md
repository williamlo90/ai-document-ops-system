# Security Remediation V7

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-010 from the 15 July 2026 security baseline
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-010: internal Prometheus metrics were unauthenticated | `CLOSED_WITH_INGRESS_REQUIREMENT` | The route requires a dedicated service credential, rejects all business credentials, and returns private no-store responses. Hosted deployment must still keep the route outside public ingress and manage the token as a secret. |

## Implemented Controls

- `GET /internal/metrics` requires `X-Metrics-Token`; missing and incorrect credentials receive a
  generic `401 Unauthorized` response.
- Metrics authentication uses constant-time comparison and does not create a user security context.
  The metrics token cannot call document, review, export, or other business APIs.
- Hosted modes require `APP_METRICS_TOKEN`, reject known defaults and values shorter than 24
  characters, and require it to differ from every server-owned role credential.
- Metrics responses use `Cache-Control: no-store, private`, `Pragma: no-cache`, and `Expires: 0`.
- The deployment contract keeps the route outside the public load balancer and injects the token
  into only the authorized collector.

## Executed Evidence

| Check | Result |
| --- | --- |
| Missing metrics token | `401 Unauthorized` |
| Incorrect metrics token | `401 Unauthorized` |
| Valid administrator access token used as metrics token | `401 Unauthorized` |
| Dedicated metrics token | `200`, Prometheus text, private no-store headers |
| Metrics token presented to business authentication | Rejected |
| Hosted missing, weak, or duplicate metrics credential | Startup policy rejected configuration |
| Affected security/API/settings/observability suite | 64 passed |
| Ruff format and lint | Passed |
| Full backend regression | 425 passed, 2 skipped |

## Residual Limitations

- Application authentication does not replace network isolation; hosted ingress must not route
  `/internal/metrics` publicly.
- Token rotation, collector configuration, secret-manager access policy, and monitoring-network
  rules require verification in the authorized deployment.
- Metrics contain aggregate route/status labels, not invoice content, but they still reveal service
  behavior and remain operationally sensitive.

## Release Decision

- Local synthetic and controlled provider evaluation: `PASS_WITH_LIMITATIONS`.
- Application-level metrics exposure: `CLOSED`.
- Hosted real-data release: still `BLOCKED` by external scanner deployment, provider governance,
  hosted infrastructure verification, and independent review.
