# ERPNext Workflow Benchmark Results

- Run dates: 21-22 August 2026
- Protocol: [ERPNext Controlled Benchmark Protocol v1.2](erpnext-benchmark-protocol.md)
- Evidence: [machine-readable result](evidence/erpnext-workflow-benchmark-v1.json)

## Result

One operator completed 20 trials using the same 10 generated synthetic invoices: once by entering
data directly into ERPNext and once through the application-assisted review workflow.

For the six invoices that were eligible to become drafts and produced verified drafts in both
methods:

| Metric                     | Manual entry | Application-assisted |
| -------------------------- | -----------: | -------------------: |
| Median elapsed time        | 74.5 seconds |           45 seconds |
| Correct expected outcomes  |         9/10 |                10/10 |
| First-pass verified drafts |          1/6 |                  6/6 |
| Outcome failures           |            1 |                    0 |

The application-assisted median was **39.6% lower**. All four intentionally blocked cases were
handled safely by the application: missing supplier, inconsistent total, invalid date order, and a
duplicate invoice. No duplicate, submitted, posted, or paid accounting transaction was created.

## What was compared

```text
Manual
Open PDF -> validate and type values in ERPNext -> save Draft -> verify

Application-assisted
Upload PDF -> review extracted values -> approve -> create ERPNext Draft -> verify
```

The timer covered operator activity and system waiting from opening or selecting the invoice until
the draft or expected blocker was verified. Login and environment startup were excluded from both
methods.

## Per-case outcomes

| Case   | Scenario                     | Manual             | Assisted       | Manual time | Assisted time |
| ------ | ---------------------------- | ------------------ | -------------- | ----------: | ------------: |
| ERP-01 | Standard USD invoice         | Verified draft     | Verified draft |        130s |           25s |
| ERP-02 | No-tax USD invoice           | Verified draft     | Verified draft |         74s |           47s |
| ERP-03 | EUR invoice                  | Verified draft     | Verified draft |        264s |           35s |
| ERP-04 | Supplier missing             | Safe blocker       | Safe blocker   |         75s |           30s |
| ERP-05 | Total mismatch               | Safe blocker       | Safe blocker   |         32s |           27s |
| ERP-06 | Due date before invoice date | Manual entry error | Safe blocker   |         68s |           27s |
| ERP-07 | Original invoice             | Verified draft     | Verified draft |         60s |           45s |
| ERP-08 | Duplicate invoice            | Safe blocker       | Safe blocker   |         76s |           40s |
| ERP-09 | Low-contrast invoice         | Verified draft     | Verified draft |         68s |           49s |
| ERP-10 | Rotated invoice              | Verified draft     | Verified draft |         75s |           45s |

Blocker cases are included in outcome success but excluded from the paired draft-time median. This
prevents a fast rejection from being treated as equivalent to creating and verifying a draft.

## Interpretation

The result supports a narrow conclusion: in this local pilot, the application reduced the median
elapsed time required to create a verified ERPNext draft and prevented the manual error observed on
the invalid-date case. It also removed manual supplier, currency, tax, and account mapping from the
assisted path.

This result does not establish production savings, multi-user usability, customer accuracy, or
return on investment. It used one operator, generated synthetic documents, a known test set, and a
local ERPNext sandbox. Active operator time and unattended system wait were not measured
separately. One assisted trial ran outside the planned crossover order, and the pilot included
implementation corrections before affected cases were rerun and verified.

## Environment

- ERPNext 16.32.0 and Frappe 16.31.0 in a local Docker sandbox;
- Mistral OCR using `mistral-ocr-latest`;
- OpenAI structured extraction using `gpt-5.4-mini-2026-03-17`;
- Windows 11, Chrome 151, and Edge 151;
- Purchase Invoice contract schema version 3;
- draft-only integration role with no submit, cancel, delete, post, or payment permission.

The private workbook retains trial-level timestamps, draft checks, corrections, ERP draft IDs, and
notes. It is intentionally excluded from Git.
