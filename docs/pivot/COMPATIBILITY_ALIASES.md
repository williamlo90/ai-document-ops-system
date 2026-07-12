# Compatibility Aliases

Status: Main Sprint 0 migration contract, 2026-07-08.

| Existing contract | Future generic contract | Migration rule |
|---|---|---|
| `GET /invoices/{id}/workflow` | `GET /documents/{id}/workflow` | Existing route remains as a compatibility alias; semantic parity tests pass |
| `GET /invoices` | Generic document-operation list/projection | Keep invoice route for current clients |
| `/invoices/{id}/retry` | Generic retry command | Both routes call one service command |
| `/invoices/{id}/reprocess` | Generic reprocess command | Preserve idempotency and audit semantics |
| `/invoices/{id}/cancel` | Generic cancel command | Preserve policy checks |
| `/invoices/{id}/request-correction` | Generic correction command | Preserve durable reason/event |
| `/invoices/{id}/escalate` | Generic escalation command | Preserve owner and waiting state |
| `invoice_review` | `document_review` | Deserialize both; serialize legacy value only on legacy contract |
| `vendor_follow_up` | `evidence_follow_up` | Map existing persisted values without destructive migration |
| `invoice_export` | `document_export` | Tool remains invoice-specific until another template exists |
| Invoice extraction payload | Generic evidence fields plus invoice details | Never fabricate source text or confidence |
| AgentOps backoffice scenarios | Document-operation scenarios | Preserve historical dataset IDs and versions |

## Alias Removal Gate

An alias may only be deprecated after:

1. Generic contract and parity tests pass.
2. Frontend no longer depends on the legacy route.
3. Runbook and API documentation identify the replacement.
4. Persisted legacy values have a reversible mapper.
5. One release cycle retains the compatibility route.
