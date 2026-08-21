# ERPNext Phase 7 Technical Verification

- Date: 2026-08-14
- Status: complete

## Scope

Phase 7 verifies the draft-only ERPNext boundary before any timed benchmark. It does not measure
business impact and does not use the locked `T01`-`T10` benchmark records.

## Evidence Matrix

| Boundary                    | Evidence                                                                                                                                               | Result |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| Explicit approval           | API and service tests reject an unapproved document before the provider call and record `erp_draft_blocked`.                                           | Passed |
| Valid approved draft        | API contract test creates one verified Draft and stores the provider ID, URL, and `docstatus = 0`.                                                     | Passed |
| Duplicate and replay        | Repeating a confirmed request returns the stored delivery; the provider create count remains one.                                                      | Passed |
| Invalid mapping             | An approved invoice with no exact supplier mapping returns `422`, records a blocked audit event, and makes no provider call.                           | Passed |
| Timeout and unknown outcome | Transport tests classify write uncertainty; API tests prevent blind resend and reconcile by the server-derived delivery key.                           | Passed |
| Restart persistence         | SQLite delivery evidence survives repository recreation; a fresh real ERPNext client finds the same Draft by delivery key.                             | Passed |
| Local-to-ERP values         | The real verifier compares company, supplier, dates, invoice number, currency, payable account, total, line values, identity fields, and Draft status. | Passed |
| Submit and payment boundary | The public ERP route inventory has no submit or payment action. The integration role has `submit = 0` and no `Payment Entry` permission.               | Passed |
| Log redaction               | API tests capture ERP operation logs and confirm that credentials, vendor, invoice number, and monetary payload values are absent.                     | Passed |

## Real-Sandbox Finding

The first real run failed because ERPNext replaced the requested `posting_date` with the current
date. The mapping now sends `set_posting_time = 1`, and the production adapter verifies
`posting_date`, `bill_date`, `due_date`, and the payable account before reporting success. The failed
verification draft was deleted automatically. A second run passed every field comparison.

## Verification Results

- Focused ERPNext suite: 35 tests passed.
- Full backend suite: 547 tests passed.
- Backend coverage: 90.95% lines and 75.05% branches.
- Real local ERPNext create: one non-benchmark Purchase Invoice retained with `docstatus = 0`.
- Fresh-client provider reconciliation: passed.
- Benchmark master-data and permission verification: passed.
- Frontend dependency audit: passed after updating two newly disclosed vulnerable packages to
  their patched versions; no exception was added.
- Full release verifier: passed, including 24 frontend tests, 29 browser tests, and one real
  full-stack browser journey.

The retained Draft and its cleanup metadata are stored under the ignored
`_private_data/erpnext-benchmark-phase7/` directory. It is for visual inspection only and must be
removed before Phase 8 measurements:

```powershell
.\.venv\Scripts\python.exe scripts\verify_erpnext_phase7.py --cleanup-kept
```

To repeat the technical verifier without retaining a Draft:

```powershell
.\.venv\Scripts\python.exe scripts\verify_erpnext_phase7.py
```

## Boundary

This evidence proves the behavior of one local ERPNext sandbox and the automated contracts in this
repository. It does not prove production ERP compatibility, accounting correctness across other
configurations, multi-user reliability, or measured time savings. Those claims remain blocked until
the later dry run, benchmark, and analysis phases are complete.
