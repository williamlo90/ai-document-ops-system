# Phase 2 — traceable data and version-bound evidence approval

Phase 2 adds invoice evidence revisions, purchasing source history, and approval
of an immutable review snapshot. It does not calculate three-way match outcomes,
reserve quantities, submit ERP transactions, or certify payment eligibility.
`posting_ready` remains false. Existing draft approval/export behavior is preserved;
historical `exported` is not relabeled `posted`.

## Data and authority

Invoice schema `invoice_v2` extends lines with persisted line ID, UOM, tax and
discount. Pipeline-assigned line IDs are deterministic within a document and are
preserved when a reviewer edits/reorders identified lines. Legacy lines without
IDs receive document/position-derived identities on evidence capture. Historical
extractions remain readable without rewriting them.

An append-only evidence revision stores raw source text when supplied, normalized
and effective values, page/excerpt, optional normalized bounding box, transform or
formula/input references, actor/time/reason and before/after changes. OCR anchors
are retained as unverified (`unknown`) until reviewer attestation. Coordinates
are never fabricated. Formula metadata and page/excerpt attestations are human
review records, not independent proof that the OCR or formula is correct. New
provider results and legacy review edits capture revisions; changed values lose
prior verification. Missing values remain null. Legacy provenance remains unknown.

Purchasing inputs have workspace/company/source-system/source-ID identity, source
version, timestamp, supplier, currency, document status, and stable source-line
references. PO and receipt records are imported atomically through validated JSON
or CSV. Duplicate versions, conflicting CSV headers, non-finite/ambiguous numbers,
and duplicate source lines are rejected. Cancellation is a new version, preserving
history. Imports are limited to 100 records, CSV to 1 MB/1,000 rows and each source
to 500 lines. JSON decimal quantities/prices must be strings (integer values also
accepted); floating-point inputs are rejected.

Administrator-verified supplier aliases, item mappings and UOM aliases have their
own versions. Alias collisions are rejected after whitespace/case normalization.
The bounded initial policy supports same-currency only, exact UOM or verified
aliases, explicit ROUND_HALF_UP, and configurable source freshness. Quantity/price
matching and conversions are intentionally reserved for Phase 3. Freshness checks sync time; source-update timestamps determine chronological
ordering, so an older unchanged PO can still be freshly verified. A successful
ERP re-read may refresh an identical source version; changed content under the
same source version is rejected.

A snapshot binds the invoice revision, full PO/receipt versions, proposed line
allocations, mapping, policy, company and source references into a canonical SHA256
payload hash. `ap_approver` or admin can approve only the current unblocked hash.
Reviewers can attest and prepare snapshots but cannot grant AP approval. Expired,
changed, cancelled or missing sources require a new snapshot and approval; old
approval records are immutable. Proposed allocations are references, not inventory
reservations. SQLite transactions and PostgreSQL workspace lock rows serialize AP
writes. Review and processing writes participate in that lock boundary.

## API and workflow

- `POST /ap/sources/import`: `{ "records": [...] }`; see
  [synthetic example](../../../examples/procurement/phase2-synthetic.json).
- `POST /ap/sources/import-csv`: `{ "content": "..." }`. Required columns:
  company,kind,source_system,source_id,source_version,supplier_id,currency,status,
  source_updated_at,source_line_id,item_id,uom,quantity,unit_price,amount.
  Receipt rows also require po_id and po_line_id. Optional tax/discount are decimals.
- `PUT /ap/mapping`: company, supplier_aliases, item_mappings, uom_mappings, reason.
- `PUT /ap/policy`: company, currency, max_age_hours, reason. Policy defaults are
  explicit in the API schema. The dated example intentionally becomes stale;
  use the actual source timestamp rather than changing it to bypass freshness.
- `POST /ap/invoices/{id}/capture`, `GET /ap/invoices/{id}` and
  `PUT /ap/invoices/{id}/evidence` expose revisions and optimistic concurrency.
- `POST /ap/invoices/{id}/snapshots`: company, expected_revision, source_system,
  po_ids, receipt_ids, allocations (`invoice-line-id: "PO-ID:PO-line-ID"`).
- `GET /ap/snapshots/{id}` rechecks freshness and current versions;
  `POST /ap/snapshots/{id}/approve` requires payload_hash and AP authority.

In Review Workspace, capture legacy values if necessary, correct line/header
values, then record the page/excerpt actually checked. Source buttons open that
page in the document's existing PDF viewer. The panel displays revision diffs,
PO/receipt evidence, source timestamps and current/stale approval status. Configure
`APP_AP_APPROVER_TOKEN` as a distinct credential to use the separate role.
Administrative purchasing imports/configuration use the API in this phase.

## Persistence and ERP boundary

SQLite schema migration 13 adds `ap_versions` and `ap_scope_locks`. PostgreSQL
migration `005_ap_evidence_versions.sql` adds equivalent tables; apply it using
the existing migration runner before starting the updated PostgreSQL application.
Both preserve existing data. Memory mode is ephemeral and used only for local tests.

`POST /ap/sources/sync-erpnext` reads exactly one named PO or receipt via GET and
uses the same import validation. It requires company, kind, source_id and explicit
IANA site_timezone for timezone-naive ERP timestamps. It validates returned source
identity/company; it cannot create, submit or cancel ERP records. Local adapter
contract tests pass. Live ERP validation was unavailable because the configured
sandbox could not be reached. No Docker service was started. PostgreSQL live tests
remain environment-dependent; they are not claimed as executed here.

## Validation and learning checkpoint

See [phase2-validation.json](phase2-validation.json). Local tests cover stale invoice,
policy and mapping versions, receipt cancellation, duplicate/malformed imports,
decimal boundaries, tenant/RBAC isolation, immutable approvals, concurrent approval,
SQLite reopen/migration, extended-line persistence, legacy correction compatibility,
ERP GET-only contract and source-page navigation. The complete existing backend
and frontend suites are rerun. Final quality holdout remains closed; no OCR/LLM
request or ERP write is needed for this phase.

The lesson is that a correct-looking invoice value is insufficient: its provenance,
source freshness and the precise approved versions must travel together. Phase 3
can now evaluate three-way matching against stable inputs without silently reusing
approval from another revision.
