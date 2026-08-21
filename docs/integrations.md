# Accounting Integration Boundary

Approved invoices can leave the application through one of two explicit paths:

- a credential-free CSV download; or
- an ERPNext Purchase Invoice created in Draft state (`docstatus = 0`).

Neither path submits, posts, pays, cancels, or deletes an accounting transaction.

## ERPNext Draft Flow

```text
approved invoice
-> deterministic ERP mapping
-> durable delivery reservation
-> ERPNext Draft create
-> response and total verification
-> provider ID and URL persisted
-> local invoice marked exported
```

The runtime sends normalized invoice values only. It never sends raw PDF bytes, OCR text, storage
keys, admin credentials, or provider traces to ERPNext.

Administrator-only endpoints:

```http
GET  /integrations/erpnext/documents/{document_id}/delivery
POST /integrations/erpnext/documents/{document_id}/draft
POST /integrations/erpnext/documents/{document_id}/delivery/reconcile
```

The create endpoint accepts no caller-supplied idempotency key. The server derives one from the
workspace, document, and approved review record, then stores the same key and mapped-payload hash
in ERPNext custom fields. Repeating a confirmed request returns the stored result without a second
provider POST.

If a create response is lost, the delivery becomes `unknown`. The application queries ERPNext by
the stable key before any retry. A missing provider record becomes a retryable known failure; one
exact matching Draft becomes a reconciled success; duplicate or mismatched provider records are
rejected.

## Safety Checks

Delivery is blocked unless all of these remain true at send time:

- the caller is an administrator;
- the document and review record are both approved;
- reviewer identity and review time are present;
- current validation has no error;
- supplier, currency, account, tax, date, and amount mappings are deterministic;
- ERPNext returns the same business and identity values;
- ERPNext returns Draft state and a matching calculated total.

The dedicated ERPNext role can read required master data and create/read Draft Purchase Invoices.
It cannot submit, cancel, delete, or manage schema.

## Delivery Evidence

The durable ledger stores the adapter, server delivery key, mapped payload hash, attempt count,
provider ID, provider URL, provider `docstatus`, provider update time, reconciliation time, and a
sanitized failure code. Key audit events include:

- `erp_draft_requested`
- `erp_draft_create_started`
- `erp_draft_created`
- `erp_draft_outcome_unknown`
- `erp_draft_reconciled`
- `erp_draft_retry_claimed`
- `erp_draft_failed`
- `erp_draft_blocked`
- `erp_draft_unsafe_state_detected`

## Legacy Adapter Contract

The generic adapter endpoint remains for isolated adapter tests:

```http
POST /integrations/accounting/documents/{document_id}/export
Idempotency-Key: caller-generated stable key
```

Its mock implementation does not represent a configured production accounting provider. CSV and
ERPNext are the user-facing export modes.
