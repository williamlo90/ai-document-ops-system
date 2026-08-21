# ERPNext Draft Integration Design

Status: accepted for Phase 6 implementation
Last reviewed: 2026-08-14
Contract version: 1

This document freezes the application-to-ERPNext boundary before implementation. The integration
creates a Purchase Invoice in Draft state for an invoice that has already passed deterministic
validation and explicit human approval. It does not submit, post, pay, cancel, or delete an ERPNext
document.

The machine-readable companion is
[`examples/erpnext/purchase_invoice_contract.json`](../examples/erpnext/purchase_invoice_contract.json).

## Decision

Use the existing integration delivery ledger, payload hash, retry claim, audit repository, and
terminal `EXPORTED` document status. Add an ERPNext-specific adapter, mapping policy, provider-backed
reconciliation, and delivery projection.

`EXPORTED` means that the application completed its controlled outbound transfer. It does not mean
that the Purchase Invoice was submitted, posted to the general ledger, paid, or otherwise finalized.
Every user-facing ERPNext success message must therefore say **ERP draft created**.

The delivery is an explicit administrator action after approval. Approval does not automatically
write to ERPNext. This keeps the accounting boundary visible and makes accidental external writes
less likely.

## Safety Invariants

The adapter must fail closed unless all of these conditions are true:

1. The caller has the application `admin` role and belongs to the document workspace.
2. The document status is `approved`.
3. A persisted review task has status `approved`, a reviewer identity, and a review timestamp.
4. The current stored extraction has no validation errors.
5. Supplier, invoice number, invoice date, due date, subtotal, total, and currency are present.
6. The supplier, account, currency, tax, and item mappings are exact configured matches.
7. The source totals and any extracted lines reconcile within USD/EUR cent precision.
8. No successful delivery or conflicting provider record already exists.

The provider response must contain the expected delivery key and payload hash, match the mapped
company, supplier, invoice number, currency, and total, and have `docstatus = 0`. A missing or unsafe
response is not a success.

The application and its integration user must never call an ERPNext submit, cancel, delete, payment,
or posting method. The dedicated `Invoice Draft Integration` role remains unable to perform those
actions even if application code regresses.

## Application API

Phase 6 adds these administrator-only routes:

| Method | Route                                                              | Purpose                                                                                         |
| ------ | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `POST` | `/integrations/erpnext/documents/{document_id}/draft`              | Reserve or replay one delivery and create a Draft Purchase Invoice when safe.                   |
| `GET`  | `/integrations/erpnext/documents/{document_id}/delivery`           | Return the current delivery state and sanitized ERP reference.                                  |
| `POST` | `/integrations/erpnext/documents/{document_id}/delivery/reconcile` | Query ERPNext by the stable delivery key and resolve an unknown outcome from provider evidence. |

The server derives the authoritative delivery key. A browser does not create a new key for each
click. Repeated requests for the same approved review resolve to the same ledger record.

A successful create response has this application shape:

```json
{
  "document_id": "11111111-1111-4111-8111-111111111111",
  "delivery": {
    "status": "succeeded",
    "display_status": "erp_draft_created",
    "attempt_count": 1,
    "replayed": false,
    "external_id": "ACC-PINV-2026-00001",
    "external_url": "http://127.0.0.1:8080/app/purchase-invoice/ACC-PINV-2026-00001",
    "provider_docstatus": 0,
    "updated_at": "2026-08-14T08:00:00+00:00"
  }
}
```

Responses and logs must not include API keys, API secrets, Authorization headers, raw provider error
HTML, or full invoice payloads.

## ERPNext Contract

The adapter uses token authentication and the resource API:

```text
POST /api/resource/Purchase%20Invoice
GET  /api/resource/Purchase%20Invoice?filters=...&fields=...
GET  /api/resource/Purchase%20Invoice/{name}
```

Creation sends `docstatus: 0` explicitly. The adapter must not follow redirects to an unapproved host.
The configured base URL must pass the existing scheme, credential, path, and host allowlist checks.

The ERPNext Administrator password is outside the runtime contract. It remains limited to the local
master-data provisioning script.

### Required Provider Fields

| ERPNext field                        | Source                                     | Rule                                                                                                                    |
| ------------------------------------ | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `company`                            | Configuration                              | `Invoice Review Assisted Benchmark` for the controlled benchmark.                                                       |
| `supplier`                           | Exact supplier mapping                     | Source vendor must map to the Assisted Benchmark supplier. No fuzzy match or invented vendor is allowed.                |
| `posting_date`                       | Local trial date                           | Use the local calendar date when the manual entry or assisted delivery runs. The two methods may run on different days. |
| `bill_no`                            | Extracted invoice number                   | Preserve the source value after whitespace normalization.                                                               |
| `bill_date`                          | Extracted invoice date                     | ISO `YYYY-MM-DD`.                                                                                                       |
| `due_date`                           | Extracted due date                         | ISO `YYYY-MM-DD`; must not be before the invoice date.                                                                  |
| `currency`                           | Extracted currency                         | Only a configured ERPNext currency is accepted. The benchmark permits USD and EUR.                                      |
| `conversion_rate`                    | Configured rate                            | `1.00` for USD; fixed `1.10` for EUR on `2026-07-03`. Never ask a model to choose a rate.                               |
| `credit_to`                          | Currency mapping                           | USD uses `Creditors - IRA`; EUR uses `Creditors EUR - IRA`.                                                             |
| `items`                              | Extracted lines or configured summary line | Must reconcile exactly to subtotal.                                                                                     |
| `taxes_and_charges`                  | Deterministic tax mapping                  | No template for 0%; Assisted 10% or 20% template for exact benchmark rates.                                             |
| `custom_invoice_review_delivery_key` | Server-derived identity                    | Unique provider lookup key.                                                                                             |
| `custom_invoice_review_document_id`  | Local document UUID                        | Traceability only.                                                                                                      |
| `custom_invoice_review_payload_hash` | Canonical payload SHA-256                  | Detects conflicting replays and supports reconciliation.                                                                |
| `docstatus`                          | Constant                                   | Always integer `0`.                                                                                                     |

Phase 6 provisions the three custom fields through the Administrator-only setup command. The runtime
integration role may set and read them but cannot create or alter ERPNext schema.

### Line Mapping

If complete extracted line items are available, each line uses the configured non-stock item
`BENCH-PROF-SVC`, its source description, source quantity, source unit price, and
`Professional Services - IRA`. The sum of line amounts must equal the source subtotal.

If no line items were extracted, the benchmark policy creates one configured summary line:

```json
{
  "item_code": "BENCH-PROF-SVC",
  "item_name": "Professional Services",
  "description": "Invoice AC-1001",
  "qty": 1,
  "uom": "Nos",
  "conversion_factor": 1,
  "rate": 100.0,
  "expense_account": "Professional Services - IRA"
}
```

The amount comes from the approved subtotal. The configured item and account are accounting
mappings, not model output. Partially extracted or arithmetically inconsistent lines block delivery;
the adapter must not silently replace suspicious lines with a summary.

### Tax Mapping

Tax is calculated only from the approved subtotal and tax amounts, then matched to one configured
benchmark rate. A zero tax amount sends no tax template. Exact 10% and 20% cases use their Assisted
Benchmark templates. A missing, negative, or unsupported rate blocks delivery.

The expected provider grand total must equal the approved source total after currency-appropriate
rounding. ERPNext calculation is verified from the create response and again on provider lookup.

## Idempotency

The stable key is:

```text
erpnext:{sha256(workspace_id + NUL + document_id + NUL + review_task_id)}
```

The complete key is stored in the local delivery ledger and
`custom_invoice_review_delivery_key`. Only a 12-character SHA-256 fingerprint may appear in logs.

The canonical payload hash covers the mapped business payload, including provider identifiers,
account mappings, item rows, tax template, and `docstatus`. It excludes credentials, timestamps,
response metadata, and the ERP-generated document name.

For a repeated request:

- same key, same document, same payload hash, local success: replay the stored success without POST;
- same key, same hash, provider draft found: verify it and reconcile to success;
- same key, different document or payload hash: block as an idempotency conflict;
- provider record with the key but unsafe state or mismatched values: block and raise an operator
  alert;
- no provider record after a failure known to occur before acceptance: claim one retry with the same
  key;
- unknown POST outcome: reconcile before any retry.

The source duplicate guard remains separate. ERPNext's supplier invoice uniqueness and the local
validation report both protect `supplier + bill_no`; the delivery key protects repeated transport of
one approved decision.

## Failure and Reconciliation Rules

| Condition                                                                   | Internal result                         | Retry rule                                | User message                           |
| --------------------------------------------------------------------------- | --------------------------------------- | ----------------------------------------- | -------------------------------------- |
| Missing approval, blocker, or mapping                                       | `failed`, permanent                     | No retry until data/configuration changes | `Not ready for ERP`                    |
| ERP authentication or permission rejection                                  | `failed`, permanent configuration error | No automatic retry                        | `ERP connection needs attention`       |
| ERP validation or duplicate rejection                                       | `failed`, permanent                     | No blind retry                            | `ERP rejected this draft`              |
| HTTP 429 before acceptance                                                  | `failed`, retryable                     | Same key, bounded retry                   | `ERP is busy. Try again.`              |
| Connection failure known before request send                                | `failed`, retryable                     | Same key, bounded retry                   | `ERP could not be reached`             |
| Timeout, reset, malformed receipt, or 5xx after POST may have been accepted | `unknown`                               | Provider lookup before retry              | `Checking whether ERP saved the draft` |
| Exact Draft found during lookup                                             | `succeeded`                             | No POST                                   | `ERP draft created`                    |
| No record found after bounded reconciliation                                | `failed`, retryable                     | Same key may be retried                   | `Draft was not found. Retry is safe.`  |
| Matching key found with changed payload or `docstatus != 0`                 | `failed`, permanent safety alert        | Never retry automatically                 | `ERP record needs manual review`       |

At most three create attempts are permitted for one delivery. Reconciliation reads do not increment
the create-attempt count. Backoff is bounded and no unknown result is converted to success from an
operator-entered external ID alone.

Provider-backed reconciliation performs these steps:

1. Query Purchase Invoice by `custom_invoice_review_delivery_key`.
2. Require zero or one result; multiple matches are a safety failure.
3. If no record exists, retain `unknown` until the bounded lookup window ends.
4. Fetch the complete candidate by name.
5. Require `docstatus = 0`, matching payload hash, and matching business fields.
6. Persist the provider name and safe URL, then mark the delivery succeeded and the document
   `EXPORTED` in one local transaction.

## Persistence

Extend `IntegrationDeliveryRecord` rather than create a parallel ERP ledger. Phase 6 adds nullable
provider evidence fields while preserving existing rows:

- `external_url`;
- `provider_docstatus`;
- `provider_updated_at`;
- `reconciled_at`;
- sanitized `error_detail` suitable for an operator;
- an explicit `replayed` value in API projection, not persisted as a business state.

The local reserve remains unique on workspace, adapter, and delivery key. A successful provider
create and the local `APPROVED -> EXPORTED` transition cannot be globally atomic, so the unknown
state and provider lookup are mandatory rather than treated as an edge case.

## Audit Events

Use provider-specific event names so the audit trail does not imply accounting posting:

| Event                             | When recorded                                                                   |
| --------------------------------- | ------------------------------------------------------------------------------- |
| `erp_draft_requested`             | Administrator requests delivery after approval.                                 |
| `erp_draft_create_started`        | The reserved delivery begins a provider POST attempt.                           |
| `erp_draft_created`               | A verified `docstatus = 0` response is persisted.                               |
| `erp_draft_reconciled`            | Provider lookup confirms a previously unknown create.                           |
| `erp_draft_retry_claimed`         | A known-safe retry is exclusively claimed.                                      |
| `erp_draft_failed`                | A sanitized retryable or permanent failure is stored.                           |
| `erp_draft_outcome_unknown`       | The provider may have accepted the POST.                                        |
| `erp_draft_blocked`               | Approval, mapping, duplicate, payload, or provider-state safety check fails.    |
| `erp_draft_unsafe_state_detected` | A matching provider document is not Draft or differs from the approved payload. |

Audit summaries may contain adapter name, attempt number, provider document name, error code, and a
delivery-key fingerprint. They must not contain secrets or the full invoice payload.

## User-Facing States

| Derived state         | Primary copy                           | Available action                      |
| --------------------- | -------------------------------------- | ------------------------------------- |
| Unapproved or blocked | `Not ready for ERP`                    | Return to review or resolve issue.    |
| Approved, no delivery | `Ready to create ERP draft`            | `Create ERP Draft`.                   |
| Pending               | `Creating ERP draft`                   | Disable duplicate action.             |
| Unknown               | `Checking whether ERP saved the draft` | `Check ERP Status`; no create retry.  |
| Retryable failure     | `ERP draft was not created`            | `Retry`.                              |
| Permanent failure     | `ERP draft needs attention`            | Show one actionable sanitized reason. |
| Success               | `ERP draft created`                    | `Open in ERPNext`.                    |

The success panel shows the ERP document ID, actor, timestamp, Draft status, and audit-event count.
It must not use `posted`, `paid`, `completed in accounting`, or similar finalization language.

## Review of Alternatives

### Automatically create a draft immediately after approval

Rejected. It hides an external accounting write inside the review action, weakens separation of
duties, and makes the benchmark's application and ERP timing harder to inspect.

### Trust the local delivery ledger after an unknown provider response

Rejected. Local state cannot prove whether ERPNext accepted a request. Provider lookup is required.

### Reconcile by supplier and invoice number only

Rejected as the primary mechanism. Those fields are business duplicate controls, but they do not
uniquely identify one transport attempt or prove payload equality. The custom delivery key and hash
are authoritative; the business fields are additional checks.

### Add `ERP_DRAFT_CREATED` to the document lifecycle

Rejected for this milestone. The existing terminal `EXPORTED` state already represents a completed
outbound transfer. Provider-specific delivery state supplies precise UI copy without expanding the
shared document state machine. This decision must be revisited if the product later supports several
simultaneous outbound destinations.

## Phase 6 Acceptance Boundary

Implementation may begin when it follows this frozen contract. Phase 6 is incomplete until:

- the adapter can only create and read Draft Purchase Invoices;
- explicit review evidence is checked in addition to document status;
- custom provider identity fields are provisioned and verified;
- the exact mapping and payload hash are deterministic;
- unknown outcomes reconcile from ERPNext before retry;
- duplicate clicks and process restarts do not create a second draft;
- API and UI use the provider-specific states and copy above;
- existing mock and CSV behavior remains covered or is deliberately migrated.
