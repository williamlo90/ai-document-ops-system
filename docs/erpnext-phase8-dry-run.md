# ERPNext Phase 8 Dry Run

Phase 8 rehearses the measurement procedure before the fixed T01-T10 benchmark begins. It uses a
separate synthetic invoice, `PHASE8-PRACTICE-001`, so practice cannot consume or contaminate a
formal case.

## Technical Preflight

An automated procedural rehearsal passed on 15 August 2026 using the configured live OCR and
extraction providers. The application extracted every expected amount and date, the reviewer path
normalized the vendor label to the configured ERP supplier, and ERPNext created a verified Draft
with `docstatus=0`. The Draft and application record were then removed. This preflight proves the
technical path is available; it is not operator timing evidence and is excluded from benchmark
results.

## Prepare

Keep ERPNext and the application running, then create the ignored practice files:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_erpnext_phase8.py prepare
```

The command writes a PDF, expected values, and a dry-run record under
`_private_data/erpnext-benchmark-phase8/`. None of these files are committed.

## Rehearse Both Workflows

Use one screen recording for each workflow. Do not consult the expected JSON until the Draft has
been saved.

### Manual

1. Start logged into a blank ERPNext Purchase Invoice.
2. Start the timer immediately before opening the practice PDF.
3. Read the PDF and enter the invoice directly into ERPNext.
4. Save a Draft, verify the values, and stop the timer.
5. Derive active human time from the recording. Reading and typing count; unattended wait does not.

### Application-assisted

1. Start logged into the application upload page with ERPNext open in another tab.
2. Start the timer immediately before selecting the practice PDF.
3. Upload, wait for extraction, review and correct the values, then approve.
4. Create the ERPNext Draft, verify it in ERPNext, and stop the timer.
5. Derive active human time using the same rule as the manual run.

Record each verified result:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_erpnext_phase8.py record manual `
  --elapsed-seconds 120.5 --active-seconds 95.2 --erp-id ACC-PINV-2026-00001

.\.venv\Scripts\python.exe scripts\prepare_erpnext_phase8.py record assisted `
  --elapsed-seconds 75.4 --active-seconds 41.8 --erp-id ACC-PINV-2026-00002
```

Replace the example times and ERP IDs with the values from the two recordings.

An interruption stays in the notes instead of being silently rerun. The dry-run times test whether
the procedure is practical; they are not benchmark results.

## Reset and Freeze

Remove only the practice Draft from local ERPNext and documents with the exact practice filename
from the local application:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_erpnext_phase8.py reset-erp
```

Then freeze the non-secret provider/model configuration, ERPNext and Frappe versions, mapping,
protocol, workbook, and source hashes:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_erpnext_phase8.py freeze
```

Freeze fails until both operator rehearsals are recorded as verified and all exact practice records
have been removed. A material change after this point requires a protocol version increment and a
restart of affected formal trials.
