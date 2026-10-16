# Optional follow-up — paired operator study

Status: **deferred, optional** under contract 2.1.0. No attempts have started;
this study does not block Phase 6 completion or Phase 7.

The technical evaluation and the operator study have separate cohorts. The study
uses 20 sealed synthetic invoice families and one operator, with 40 timed conditions:
manual first for ten invoices and assisted first for ten. No time reduction for
this extended workflow is claimed before all scheduled conditions are scored.
The existing six-invoice verified-draft timing benchmark remains separate.

## Preparation outside the clock

Codex starts the existing ERP sandbox and the isolated study app, checks readiness,
and explains both workflows using development examples. The operator records prior
familiarity once. Practice, account login, source provisioning and fixture reset are
outside the measured task. Do not inspect study answers or practice study invoices.

The ignored workspace contains renamed upload PDFs, verified supplier/item/account
mappings and only assisted-condition purchasing sources. Manual and assisted runs
use separate PO/receipt instances. ERP supplier-invoice duplicate checking stays
enabled. The first condition's captured target is cancelled, or its unsubmitted
draft deleted, after evidence collection and before the second timer. Read-back and
GL evidence remain immutable as of completion. These sandbox resets are recorded
separately and are not part of the operator's handling time.

Run the app from the repository root:

```powershell
.venv\Scripts\python.exe scripts/phase6_study_workspace.py serve _local_docs/phase6-evaluation-cell _local_docs/phase6-human-study-cell
```

Open `http://127.0.0.1:8000` for the review app and `http://127.0.0.1:8080` for
ERPNext. Access tokens remain in the ignored `.env`; never copy them into reports.
This study has a single operator performing the required review/approval roles;
it does not demonstrate organizational separation of duties between two humans.

## Timed work

Codex presents the next scheduled PDF and that condition's purchasing source IDs.
The timer begins before reading the invoice. Use `p` only while waiting for the
system and `r` when active work resumes. Reading, checking, typing, corrections,
source verification, decisions and approvals are active work. The timer records
both active and total elapsed time; failures and skipped attempts remain scheduled.

```powershell
.venv\Scripts\python.exe scripts/phase6_time_study_timer.py _local_docs/phase6-time-study-cell.json --operator William
```

For the manual condition, enter the invoice in ERPNext from the PDF, compare it
with the assigned PO and receipt, and make the decision. A payable invoice must
be submitted and verified against the full invoice and GL, not merely saved as a
draft. A non-payable invoice ends with an explicit, reasoned operator rejection
referencing the purchasing sources; keep an ERP draft for final-field scoring.
Codex records that human decision while the clock is running. The decision file
contains the document ID, `condition: manual`, and a `dispositions` list with
`code`, `state: rejected`, `authorizer`, `reason`, `at` and `evidence_refs`.
Codex does not supply the decision or correct the operator's entered values.

For the assisted condition, upload the renamed PDF to the review app. Codex
captures the original provider extraction before any corrections. The operator
checks and corrects fields, captures the current evidence revision, verifies
required fields against page/excerpt evidence, selects the assigned purchasing
sources and line allocation, and prepares/approves the evidence snapshot. Then
assess the match. Payable cases require match approval, a verified ERP draft,
separate submit approval, and submitted invoice/GL verification. Non-payable cases
require `Reject invoice` for every current blocking issue, with owner, reason and
evidence reference. `needs_info`, a note and a correct unresolved hold are not
completed outcomes. Codex may collect outputs but must not perform the operator's
timed review, correction, approval or rejection actions.

Stop with `done` only at `posted_verified` or `exception_resolved`. A failure uses
`skip` or `failed`; do not restart silently. An interrupted timer requires an
explicit failed-attempt record before continuing. Final scoring retains every
scheduled pair, including provider failures.

## Collection and scoring

Codex runs `phase6_study_capture.py` to preserve original extraction, actual final
reviewed fields, authorized dispositions, ERP invoice and GL read-backs. For
assisted capture use the app document ID and isolated workspace; use
`--original-only` before edits. For manual capture use the ERP target and, for a
rejection, `--decision-file`. Capture files are never overwritten.

Codex links each final capture in the worksheet's `erp_readback_reference` and
copies its actual `predicted_fields`; assisted rows also retain the original
capture reference and unedited original fields. A bare ERP ID is insufficient.
Once the first timer is stopped and its proof is verified, Codex can run:

```powershell
.venv\Scripts\python.exe scripts/phase6_study_reset.py _local_docs/phase6-evaluation-cell _local_docs/phase6-time-study-cell.json DOCUMENT_ID
```

After all conditions, `phase6_time_study.py score` checks the frozen cohort,
counterbalanced order, finite timings, original/final quality and independent
terminal evidence. It reports original assisted quality separately from final
reviewed quality on the same 20 invoices. A time reduction is withheld unless
both conditions have 20 correctly completed, fully correct invoices with valid
evidence. Results describe this single-operator synthetic sandbox sample.

The technical report does not start this study. Phase 6 is checkpointed on its
technical evidence. A later operator study requires its own explicit start and
evidence before any time-reduction claim.
