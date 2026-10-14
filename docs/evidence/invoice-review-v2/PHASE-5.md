# Phase 5 — sandbox ERPNext posting

The AP path now advances beyond the Phase 3 draft-only boundary. A current approved match can
create a verified `docstatus=0` Purchase Invoice; a **separate** submit approval then permits a
sandbox submit. `posted_verified` requires a `docstatus=1` document read-back and GL evidence.
The workflow has no Payment Entry command. The legacy benchmark draft adapter is separate.

## Decisions and operator path

1. An administrator enables `ACCOUNTING_PROVIDER=erpnext`, `ACCOUNTING_SANDBOX_MODE=true` and
   `ERPNEXT_SANDBOX_POSTING_ENABLED=true` in the ignored local `.env`. The new flag defaults to
   false. The configured host is allowlisted. The ERP integration role needs Purchase Invoice
   create/read/submit and GL Entry read; it receives no Payment Entry capability. The local
   sandbox role can be provisioned with `scripts/enable_phase5_erp_permissions.py`.
2. An administrator uses `PUT /ap/posting-profile` for an append-only company mapping of
   supplier, item, expense/payable/tax accounts and currency exchange rates. Purchase Order and
   Receipt links come from the approved source snapshot. ERP company must match both live
   purchasing documents. Configure the profile against verified sandbox master data.
3. A current AP match and active quantity reservation are required. The review page shows the
   sandbox status and `Create and verify ERP draft`. The service checks live PO/Receipt versions,
   item identities, quantities and PO billed amount before writing. It computes the expected
   invoice from reviewed evidence independently of the ERP response, saves a pending operation,
   then creates and reads back the full draft: header, item count/order, quantities, rates,
   accounts, PO/Receipt links, tax, discount, exchange rate and totals.
4. An AP approver records a distinct reasoned submit approval, bound to the match basis,
   profile version, ERP target and draft verification hash. Immediately before submit, the
   service checks capability, current match/profile/source and unchanged draft. Submit uses
   that same ERP ID. The submitted document and GL rows are read back; company, voucher,
   payable, expense/tax accounts and balance must reconcile to the independent expectation.
5. `GET /ap/posting/{match_id}` exposes draft, approval and submit states. A failed or ambiguous
   delivery is never labelled posted. `POST /ap/posting/{match_id}/reconcile/{create|submit}`
   looks up the known target or unique delivery key and verifies it without another write.
   A stranded targetless create can be retried with its original key only after an administrator
   confirms absence with two ERP lookups after a visibility delay. The remote delivery key is
   unique in the provisioned sandbox; duplicate requests and restart replay use the saved
   operation. A mismatch requires reconciliation rather than an automatic second submit.

## Evidence and boundary

The focused suite injects lost create/submit responses, a crash before create, restart replay,
edited drafts, changed policy/receipt, a billed PO, cross-company mapping, permission failures,
duplicate approval and ledger mismatch. It passed on SQLite and an isolated PostgreSQL database.
The full backend suite, frontend tests/build and lint checks also passed. The guarded local
ERPNext run created one synthetic invoice `ACC-PINV-2026-00015`, verified its draft, submitted it
after separate approval, read back `docstatus=1` and two balanced GL entries, and replayed after
a process restart to the same target. The local persistent operation ledger and detailed live
report are ignored; [phase5-validation.json](phase5-validation.json) records the non-secret
checkpoint evidence.

This is a sandbox proof for one zero-tax, single-line synthetic invoice, not production payment
or posting accuracy evidence. Tax, discounts, non-unit exchange rates and multiple receipt lines
are modelled and checked in code but have not received a live ERP posting run. The next phase
freezes a holdout and measures end-to-end correctness and completion denominators.
