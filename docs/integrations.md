# Integration Boundary

Outbound integration is kept separate from CSV export and document processing.

The first supported target is a mock accounting adapter. It represents the shape of an ERP/accounting handoff without requiring real third-party credentials in the portfolio artifact.

## Current Flow

```text
approved document
-> integration service
-> invoice payload mapping
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
X-Workspace-Id: optional workspace scope
X-User-Id: optional actor id
X-Role: optional role, must resolve to admin capability
```

Only `approved` documents can be sent. A successful send marks the document `exported`.

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

## Deferred

- real webhook adapter
- real accounting/ERP credentials
- persisted outbound delivery queue
- exponential retry scheduler
- idempotency keys against external systems
- signed callback verification
