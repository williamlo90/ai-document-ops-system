# ERPNext Benchmark Master Data

Status: provisioned and verified
Last verified: 2026-08-14

Phase 4 prepares repeatable ERPNext master data for the controlled manual-versus-assisted
benchmark. It creates no Purchase Invoice and never submits, posts, or pays anything.

## Locked Dataset

- Dataset: `invoice-manual-benchmark-t01-t10`
- Source task: `019fd72c-a003-77d0-bfcf-57313c964d32`
- Fingerprint: `ca37538cd0f823acf811f23b92ffcda9e74c56000ed7f580def37bee75420407`
- Machine-readable mapping:
  [`examples/erpnext/benchmark_cases.json`](../examples/erpnext/benchmark_cases.json)
- Fingerprint algorithm: sort by benchmark alias, then hash each UTF-8 alias, a NUL byte, the PDF
  bytes, and another NUL byte.

The renamed local benchmark pack and result workbook remain under ignored directories. The source
documents are already-public synthetic fixtures in this repository, not real vendor invoices.

## ERP Structure

| Purpose                       | ERPNext record                                                          |
| ----------------------------- | ----------------------------------------------------------------------- |
| Manual workflow               | `Invoice Review Manual Benchmark` (`IRM`)                               |
| Application-assisted workflow | `Invoice Review Assisted Benchmark` (`IRA`)                             |
| Purchase line                 | `BENCH-PROF-SVC` / Professional Services                                |
| Expense accounts              | `Professional Services - IRM` and `Professional Services - IRA`         |
| USD payable accounts          | `Creditors - IRM` and `Creditors - IRA`                                 |
| EUR payable accounts          | `Creditors EUR - IRM` and `Creditors EUR - IRA`                         |
| Tax behavior                  | no row for 0%; dedicated 10% and 20% purchase-tax templates per company |
| EUR conversion                | fixed 1 EUR = 1.10 USD on 2026-07-03                                    |
| Duplicate guard               | ERPNext supplier invoice uniqueness enabled                             |

Purchase Invoice also has three Administrator-provisioned identity fields used by the runtime:

- `custom_invoice_review_delivery_key` (unique);
- `custom_invoice_review_document_id`;
- `custom_invoice_review_payload_hash`.

ERPNext v16 checks duplicate supplier invoice numbers across the fiscal year without including
company in that lookup. Each source vendor therefore maps to one Manual Supplier and one Assisted
Supplier. This keeps the source invoice number unchanged, avoids collisions between methods, and
still lets `T07`/`T08` exercise duplicate protection within each method.

## Case Matrix

| Case  | Source scenario              | ERP outcome                                                   |
| ----- | ---------------------------- | ------------------------------------------------------------- |
| `T01` | Standard USD                 | Draft eligible                                                |
| `T02` | Zero-tax USD                 | Draft eligible                                                |
| `T03` | European number format, EUR  | Draft eligible                                                |
| `T04` | Missing vendor               | Block: Supplier must not be invented                          |
| `T05` | Total mismatch               | Block: accounting lines cannot reconcile to the printed total |
| `T06` | Due date before invoice date | Block: invalid date order                                     |
| `T07` | Duplicate original           | Draft eligible                                                |
| `T08` | Duplicate copy               | Block: duplicate supplier invoice                             |
| `T09` | Low-contrast scan            | Draft eligible                                                |
| `T10` | Rotated invoice              | Draft eligible                                                |

The safe outcome is six draft-eligible cases and four intentional blockers. Reporting all 10 as
successful draft creations would conceal the controls the dataset was designed to test.

## Access Boundary

The integration user has only the custom `Invoice Draft Integration` role:

- read the master data required for mapping;
- read, create, and update Draft Purchase Invoices;
- no submit, cancel, delete, or System Manager permission.

Administrator credentials are required only by the local provisioning command and remain in the
ignored `.env`. Runtime application settings do not expose or load that password.

## Reproduce

With ERPNext running at `http://127.0.0.1:8080`:

```powershell
.\.venv\Scripts\python.exe scripts\provision_erpnext_master_data.py
.\.venv\Scripts\python.exe scripts\smoke_erpnext.py
```

The first command validates source hashes, provisions missing records, rejects conflicting existing
records, verifies the draft-only role, and writes
`_private_data/erpnext-benchmark-phase4/master-data-report.json`. Running it again is a no-op except
for re-verification.

Verified state on 2026-08-14:

- 2 benchmark companies;
- 16 method-specific Supplier mappings for 8 source vendors;
- 1 non-stock service item;
- dedicated expense, payable, and benchmark tax mappings for both companies;
- USD and EUR enabled with the fixed buying rate;
- integration-token reads passed;
- one non-benchmark Draft create/read/reconciliation smoke passed and was removed;
- 0 Purchase Invoices created.
