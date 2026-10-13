# ERP read-only preflight and execution profile

Verified 2026-10-13 using the configured integration account on the existing local
sandbox. Runtime versions: ERPNext 16.32.0, Frappe 16.31.0 (bench version).
Sanitized observations: [erp-capabilities.json](erp-capabilities.json).

| Check                                            | Result                                                                             |
| ------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Health and authenticated identity                | HTTP 200; identity matches configured integration user                             |
| Purchase Invoice list and record read            | HTTP 200; existing draft docstatus=0, modified timestamp and item fields available |
| Purchase Invoice read/create permission          | Allowed by permission endpoint; no write executed                                  |
| Purchase Invoice submit/cancel/delete permission | Denied by permission endpoint                                                      |
| Purchase Order, Purchase Receipt, GL Entry reads | HTTP 403; read permissions confirmed false                                         |

No business document was created, edited, submitted or deleted. Initial connection
attempts failed while required services were stopped. Started only existing db,
redis-cache, redis-queue and backend containers; stopped these four afterward,
preserving volumes. Frontend/scheduler/websocket were already running when checked
and were left untouched. No new image, installation or cloud resource was created.

Permission probes initially returned 500 because docname was omitted. The installed
function signature was inspected and probes repeated correctly. HTTP 500 was not
interpreted as a permission decision. No Administrator escalation was used.

## Installed source contract and remaining prerequisites

Installed `frappe.client.submit(doc)` accepts a JSON string or object, loads the
document, invokes `doc.submit()` and returns its dictionary. Candidate RPC path:
`/api/method/frappe.client.submit`. This was source inspection, not a submit test.
Installed Purchase Invoice Item schema includes purchase_order and purchase_receipt
references. The readable existing draft was not PO-backed; populated links and
actual PO/receipt/ledger record shapes remain unverified under this account.

Phase 2 must add explicitly scoped read access and synthetic PO/receipt fixtures,
then verify source versions and line linkage using the integration identity.
Phase 5 must configure a separate controlled submit capability, ledger read access,
and verify actual create/submit/read-back/idempotency using synthetic transactions.
Read-only permission metadata does not prove that a write will succeed. No current
posting correctness claim is supported. These are now known implementation
prerequisites, not unresolved connectivity assumptions.

References: [Frappe REST API](https://docs.frappe.io/framework/user/en/api/rest) and
[ERPNext Purchase Invoice](https://docs.frappe.io/erpnext/purchase-invoice).
The installed source and runtime observations take precedence over example APIs.

## Resource and cost decisions

Phase 0: read-only localhost probes; zero paid provider calls and no cloud resources.
Phases 1–6: local Python/SQLite and frontend, mock providers for broad regression;
start no full Docker stack by default. Phase 1 actual-provider diagnostic gets a
separate preflight with <=5 synthetic/licensed one-page invoices, <=10 primary
provider calls, no automatic rerun, and estimated budget <=USD 1.00. Estimate with
current model pricing before calls; stop if cost cannot be bounded or exceeds cap.
This budget is a proposed execution ceiling, not a cost already incurred.

Phase 7: resource-limited Docker release validation after code freeze. Initial
combined application profile cap: 2 CPU / 3 GiB RAM, 30-minute session; PostgreSQL
integration tested in a separate bounded run. Measure ERP stack needs before adding
it; do not start all services together on an insufficient machine. Stop only
services started for the validation; never delete persistent volumes as teardown.
Phase 8 cloud defaults to skipped unless an unmet claim needs cloud evidence and a
specific budget/teardown package has been approved. Local results are not cloud SLOs.
