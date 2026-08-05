# Integration Boundary

Outbound integration is kept separate from CSV export and document processing.

The first supported target is a mock accounting adapter. It represents the shape of an ERP/accounting handoff without requiring real third-party credentials in the portfolio artifact.

## Current Flow

```text
approved document
-> integration service
-> invoice payload mapping
-> durable delivery reservation
-> accounting adapter
-> audit attempt
-> audit success or failure
-> exported status only after successful delivery
```

## Endpoint

```http
POST /integrations/accounting/documents/{document_id}/export
```

Required headers:

```text
X-Admin-Token: ...
Idempotency-Key: caller-generated stable key, 8-128 safe characters
```

An authenticated admin session can replace `X-Admin-Token`. Identity, role, and workspace are resolved
from the server-owned credential or session, not caller-asserted identity headers.

Only `approved` documents can start a delivery. A successful send marks the document `exported`.
Replaying the same key and payload returns the stored success without invoking the adapter again.

## Payload Boundary

The integration payload contains normalized invoice fields only:

- document id
- workspace id
- vendor name
- invoice number
- invoice and due dates
- subtotal, tax, total, and currency
- line items

The adapter does not receive raw PDF bytes, OCR text, storage keys, admin tokens, or provider traces.

## Audit Events

Every integration attempt records audit events:

- `integration_export_attempted`
- `integration_export_succeeded`
- `integration_export_failed`
- `document_exported` after successful delivery

Failed delivery keeps the document `approved` so the export can be retried.

## Idempotency And Reconciliation

- The ledger reserves the workspace, adapter, document, payload hash, and key before outbound I/O.
- A known pre-acceptance failure may be retried only with the same key.
- A timeout or crash with an uncertain provider outcome is marked `unknown` or remains `pending`.
- Pending and unknown records cannot be resent automatically.
- An admin must verify the provider ledger and call
  `POST /integrations/accounting/deliveries/reconcile` with the same `Idempotency-Key`, a reason, and
  the confirmed outcome.
- A successful delivery record is persisted before the local document transition, allowing a replay
  to finish local recovery after a process interruption.

The current mock adapter honors keys. A future real adapter is not acceptable until the external
provider also binds the same key or exposes a reliable lookup/reconciliation contract.

## Deferred

- real webhook adapter
- real accounting/ERP credentials
- exponential retry scheduler
- real-provider idempotency and reconciliation verification
- signed callback verification
