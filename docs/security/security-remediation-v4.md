# Security Remediation V4

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-007 from the 15 July 2026 security baseline
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-007: outbound accounting delivery lacks durable idempotency | `CLOSED_WITH_ADAPTER_LIMITATION` | The application has a persistent delivery ledger, atomic initial reservation, stable payload binding, deterministic replay, bounded retry, and admin reconciliation. The mock adapter honors keys; a real provider contract is not yet verified. |

## Implemented Controls

- `Idempotency-Key` is required for the accounting export API and is validated as 8-128 safe
  characters.
- A workspace-scoped unique ledger record binds the key to the adapter, document, and canonical
  payload hash before any outbound call.
- Concurrent initial requests converge on one reservation. A second request that observes `pending`
  stops instead of sending.
- Successful provider acceptance is persisted before the document transitions to `exported`.
- A repeated successful request returns the stored external id without another adapter call.
- A known pre-acceptance, retryable failure can be claimed once and retried with the same key.
- An ambiguous timeout is recorded as `unknown`; a crash before a final ledger update leaves
  `pending`. Both states prohibit automatic resend.
- Admin reconciliation records a reason and either the confirmed external id or a confirmed failed
  outcome. Only a confirmed failed outcome re-enables retry.
- Idempotency-key fingerprints, attempt numbers, outcome certainty, and reconciliation are included
  in document audit events without logging the raw key.
- Document retention purge removes associated delivery records.

## Executed Evidence

| Check | Result |
| --- | --- |
| Integration service tests | 10 passed |
| API regression tests | 29 passed |
| Retention tests | 4 passed |
| Ruff on affected backend files | Passed |
| Full backend regression | 419 passed |

Covered cases include successful delivery, success replay without duplicate send, key/payload
conflict, retryable pre-acceptance failure, ambiguous post-acceptance timeout, manual success
reconciliation, workspace and role isolation, required API key, and SQLite repository recreation.

## Residual Limitations

- Only the mock accounting adapter exists. No external provider idempotency SLA, lookup endpoint, or
  reconciliation semantics have been verified.
- The local SQLite ledger is appropriate for the portfolio deployment. A horizontally scaled
  production deployment needs a transactional shared database and provider-specific integration.
- Reconciliation is deliberately manual because guessing after an ambiguous outcome is unsafe.
- Independent security review and fault-injection against a real provider remain outstanding.

## Release Decision

- Local synthetic portfolio workflow: `PASS_WITH_LIMITATIONS`.
- Real accounting delivery: `BLOCKED` until the chosen provider proves key propagation, duplicate
  suppression, outcome lookup, and reconciliation behavior in executed tests.
