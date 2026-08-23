# ERPNext Controlled Benchmark Protocol

Protocol version: 1.2
Frozen: 2026-08-21
Status: method frozen; formal comparison pending

## Question

For one operator and the fixed 10 synthetic benchmark invoices, how does the application-assisted
workflow compare with direct manual entry when producing a verified ERPNext draft Purchase Invoice?

The benchmark measures workflow time and draft correctness. It does not measure production impact,
multi-user usability, or new extraction accuracy.

Results are published only after both workflows complete this protocol. Private timing records and
screen recordings remain outside Git.

## Test Set

- Exactly 10 invoices selected in Codex task `019fd72c-a003-77d0-bfcf-57313c964d32` are used.
- Dataset fingerprint:
  `ca37538cd0f823acf811f23b92ffcda9e74c56000ed7f580def37bee75420407`.
- The mapping is locked as `T01` through `T10` in
  [`examples/erpnext/benchmark_cases.json`](../examples/erpnext/benchmark_cases.json). Do not change
  it after a formal trial starts.
- Private benchmark copies, result workbooks, and screen recordings remain outside Git. The source
  PDFs and expected records are existing synthetic fixtures under `examples/benchmark`.
- Do not consult golden labels during data entry or review. Use them only after a draft has been
  saved, if needed to adjudicate an ambiguous source value.
- These invoices have already been evaluated. This run is a workflow benchmark, not a fresh blind
  holdout.
- Six cases are draft-eligible. Four are intentional safe blockers: missing supplier (`T04`), total
  mismatch (`T05`), invalid date order (`T06`), and duplicate invoice (`T08`). A blocker must not be
  turned into a draft by inventing or changing source values.

## Workflows

### Manual

1. Start from a logged-in ERPNext blank Purchase Invoice form.
2. Start recording and the elapsed timer immediately before the first action that opens the assigned
   PDF.
3. Read the PDF, apply the frozen validation checklist, and enter eligible values directly into
   ERPNext. Do not use a spreadsheet, OCR result, or golden label as an input source.
4. For an eligible invoice, save the Purchase Invoice as Draft and verify it against the PDF.
5. For an intentional blocker, record the blocker and verify that no draft was created.
6. Stop the elapsed timer when the draft or safe blocker is verified.

### Application-assisted

1. Start from the logged-in application upload screen with ERPNext available in a separate tab.
2. Start recording and the elapsed timer immediately before the first action that selects the
   assigned PDF.
3. Upload the PDF, wait for extraction, review the source and extracted values, and correct values
   when necessary.
4. For an eligible invoice, approve it and create the ERPNext draft through the application.
5. For an intentional blocker, verify that delivery remains blocked and no ERP draft exists.
6. Stop the elapsed timer when the draft or safe blocker is verified.

## Environment Controls

- Use the same computer, browser, network, ERPNext instance, operator, display, and input devices.
- Log in and open required applications before each timed trial. Login and environment startup are
  excluded from both methods.
- Clear method-specific form state before each trial.
- Keep master-data mappings fixed for both methods.
- Use the local calendar date of each trial as ERPNext `Posting Date`. Keep Supplier Invoice Date
  and Due Date equal to the source PDF. A paired manual and assisted trial may therefore have
  different posting dates when they run on different days.
- Use the dedicated manual and assisted benchmark companies and their method-specific Supplier
  records. Keep source invoice numbers unchanged.
- Disable unrelated notifications and do not multitask during a trial.
- Record provider and ERP outages; do not silently exclude them.

## Trial Order

This is a paired, order-balanced, single-operator benchmark. Every invoice is completed once with
each method.

### Session A

1. `ERP-01` to `ERP-05`: Manual
2. `ERP-06` to `ERP-10`: Application-assisted

### Session B

Run at least 24 hours after Session A:

1. `ERP-10` to `ERP-06`: Manual
2. `ERP-05` to `ERP-01`: Application-assisted

Within a session, use the stated order. Do not reorder cases after seeing a difficult invoice or a
failure. The delay and reversed order reduce, but do not eliminate, memory, learning, and fatigue
bias.

## Timing Rules

### Elapsed time

Elapsed time includes all operator work and all system waiting between the defined start and stop
events. Record start and verified timestamps with seconds. The workbook calculates:

```text
elapsed seconds = (verified timestamp - start timestamp) * 86,400
```

### Active human time

Use the screen recording after each session to total intervals spent opening or reading the PDF,
typing, clicking, reviewing, correcting, and verifying. Exclude only unattended system waits where
the operator performs no benchmark work. Reading without keyboard or mouse input still counts as
active time.

Record active time in seconds. The workbook calculates system-wait time as elapsed time minus active
human time. Active time must never exceed elapsed time.

Pausing a timer is not allowed. If interrupted by an unrelated event, mark the trial `Interrupted`;
do not include its duration in the primary comparison and do not rerun it as though it never
happened.

## Draft Verification

An eligible-draft trial passes only when all required checks pass:

1. ERPNext document exists and has Draft status (`docstatus = 0`).
2. Exactly one ERPNext draft exists for the trial.
3. Supplier mapping is correct.
4. Invoice number is correct.
5. Invoice date is correct.
6. Due date is correct, including a genuinely absent due date.
7. Currency is correct.
8. Subtotal or net total is correct.
9. Tax total is correct.
10. Grand total is correct.
11. Required accounting line data reconciles to the approved subtotal and total.

An intentional-blocker trial passes only when the expected blocker is recorded and no ERPNext
Purchase Invoice exists for that case and method. Blocker trials remain part of safe-outcome and
failure reporting but do not enter the paired draft-completion-time metric.

Amounts use exact currency values after normal currency rounding. Dates use the date printed on the
source. A source field that is genuinely absent passes only when the saved draft follows the frozen
mapping rule for absent values; it must not be invented.

## Corrections and First-Pass Success

- A correction is one field whose initially entered or extracted value is changed before final
  verification. Count fields, not keystrokes.
- `First-pass success` means the first saved/created ERPNext draft passes every required check without
  correcting the draft, retrying delivery, or creating a replacement draft.
- Corrections made in the application before approval still count as corrections, even if the ERP
  draft is correct on its first creation.
- Record technical attempts separately from field corrections.

## Failures

Use one frozen failure category:

- `None`
- `Interrupted`
- `Source ambiguous`
- `Manual entry error`
- `Extraction error`
- `Validation blocked`
- `Mapping error`
- `Provider unavailable`
- `ERP unavailable`
- `Delivery unknown`
- `Duplicate created`
- `Unsafe non-draft state`
- `Other`

Retain the first formal outcome. A later diagnostic rerun may be recorded separately but must not
replace it. A trial with no verified draft has no completion time.

## Metrics

Primary metrics:

- median elapsed time for paired successful invoices;
- median active human time for paired successful invoices;
- paired elapsed-time reduction;
- paired active-human-time reduction;
- verified-draft completion rate for each method.
- correct safe-terminal-outcome rate across all 10 cases.

Secondary metrics:

- overall draft pass rate;
- first-pass success rate;
- median correction count;
- failure count and taxonomy;
- duplicate and unsafe-state count.

```text
time reduction = (manual median - assisted median) / manual median
```

Only invoices with successful verified drafts in both methods enter the paired time comparison.
Always report that paired sample size beside the medians. Completion and failure rates use all 10
trials per method, preventing failed cases from disappearing from the report.

## Dry Run and Freeze Rule

- Use `sample_invoice.pdf` or another non-benchmark synthetic fixture for the dry run.
- Do not use any of the 10 formal benchmark invoices for practice.
- After the dry run, freeze application code, provider/model configuration, ERPNext configuration,
  master-data mapping, protocol version, and workbook structure.
- If a material change is necessary, increment the protocol version and restart all affected formal
  trials. Do not mix incompatible configurations in one headline result.

## Reporting Boundary

The final report must state:

- one operator performed the benchmark;
- the documents were generated synthetic invoices;
- the same 10 invoices were used for both methods;
- the set was already known from earlier extraction evaluation;
- paired sample size and method completion rates;
- provider/model and ERPNext versions;
- material failures and protocol deviations.

Permitted wording after results exist:

> Across a controlled 10-invoice benchmark conducted by one operator, the application reduced the
> median time from opening an invoice to a verified ERPNext draft from X seconds to Y seconds, a Z%
> reduction. N of 6 draft-eligible invoices produced verified drafts with both methods; all four
> intentionally invalid or duplicate cases were reported separately.
