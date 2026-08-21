# AI-Powered Invoice Review & Approval System - Case Study

## Summary

Finance reviewers need to compare invoice PDFs with extracted data, catch incorrect or missing
values, and record a decision before approved data moves downstream. A missing field can slow the
workflow down. An incorrect approval can send bad data into an accounting process.

The system keeps the PDF, extracted fields, validation results, and reviewer decision in one
workflow. AI reads the document and proposes structured data. Application rules check that data. A
human reviewer makes the final decision.

## Project ownership

This is a solo portfolio project. The first complete product version was built between 12 and 28
July 2026, with maintenance and hardening continuing after that release.

The work included:

- product scope;
- architecture and implementation direction;
- evaluation design;
- failure analysis;
- documentation;
- release checks.

The original scope covered a broad document-operations platform. Repeated UI reviews showed that
workflow-engine concepts made ordinary invoice review harder to understand. Those reviews led to a
narrower product built around one complete invoice journey.

The resulting product decisions were:

- keep invoice as the only complete document type instead of adding a shallow second workflow;
- never approve an invoice from model confidence alone;
- place the PDF beside editable fields and validation errors;
- retain the original extraction when a reviewer changes a value;
- keep evaluation, provider cost, and operational details under administrator navigation;
- keep existing internal API names because renaming them would add migration risk without changing
  product behavior.

The current scope excludes a chatbot, unrestricted autonomous actions, payment execution, and
production integrations. None would improve the core review workflow at this stage.

## The user and the constraint

The primary user is a finance reviewer or accounts-payable operator handling incoming invoices.

OCR and language models can return incomplete, ambiguous, or incorrect data. The product therefore
shows uncertainty and validation errors instead of hiding them behind an automatic approval.

## The manual workflow

Without one review workspace, a reviewer typically needs to:

1. open the source PDF;
2. copy or compare invoice fields;
3. inspect totals and line items;
4. decide whether missing or inconsistent values need follow-up;
5. communicate the result;
6. keep a record of the decision.

This workflow has not been measured against a manual baseline. Its current purpose is to keep the
source document, proposed fields, validation reasons, and review action in one place.

## The implemented workflow

```text
Uploader submits invoice
-> OCR provider reads the pages
-> extraction model proposes invoice fields
-> deterministic rules check fields and totals
-> clean invoice waits for a reviewer
-> blocked invoice returns for correction
-> reviewer compares the PDF with the data
-> decision and audit events are saved
-> approved invoice becomes eligible for export
```

## What AI does

- reads invoice pages;
- maps the document content into the invoice schema;
- returns confidence and source information when the provider supports it.

The extraction prompt tells the model not to guess missing values. A seller-context guard also
rejects an ambiguous vendor name when the returned text does not provide enough support.

## What application rules do

- check required fields and normalize values;
- compare subtotal, tax, total, and line items;
- detect duplicate vendor and invoice-number pairs within a workspace;
- control retries and terminal processing states;
- enforce roles, workspaces, and valid state transitions;
- block approval while validation errors remain;
- block export until a reviewer approves the invoice.

## What the reviewer controls

- verify extracted values against the PDF;
- correct a value when the document supports the change;
- approve a clean invoice;
- reject an invalid invoice;
- request a correction when information is missing or inconsistent.

The model cannot make any of these decisions.

## Results

### Sealed licensed-synthetic holdout

The primary quality result comes from a sealed 10-invoice holdout selected from a licensed
synthetic FATURA pack. Mistral OCR and OpenAI extraction completed all 10 documents.

- **98.75% exact field match (79/80)**;
- **100% validation-code match**;
- **100% approval-blocker match**;
- 90% exact-document match (9/10).

One compressed invoice received a due date that was not present in the golden label. The error did
not change the expected validation code or approval blocker, but it remains a genuine model
hallucination. The holdout is licensed synthetic data, not customer traffic, so this is not a
production-accuracy claim.

### Diagnostic and failure example

The committed diagnostic set contains 20 synthetic PDFs covering clean cases, missing values,
arithmetic mismatches, duplicates, low-contrast scans, rotation, and a multi-page invoice. A clean
diagnostic later matched 160 of 160 labeled fields and every expected validation and blocker
outcome. That result is useful for regression work, but it is secondary because the set was already
used during development.

Before the clean rerun, one diagnostic stopped at 19 of 20 documents because the extractor returned
a localized amount such as `1.250,00` and the decimal parser rejected it. The failed artifact was
retained, deterministic number normalization was added, and a regression test covered the case
before the diagnostic ran again. No partial score was promoted as a pass.

### ERPNext workflow pilot

One operator processed the same 10 generated synthetic invoices through direct ERPNext entry and
the application-assisted workflow. Six cases were eligible to become drafts; four were expected
safe blockers. Among the six matched draft pairs, median elapsed time fell from **74.5 seconds to
45 seconds**, a **39.6% reduction**. The application produced the expected safe or draft outcome in
**10/10 cases**, compared with **9/10** for manual entry, and all six assisted drafts passed on their
first creation.

The integration created only ERPNext Purchase Invoice Drafts. It did not submit, post, pay, cancel,
or delete accounting transactions. Full method, case outcomes, and scope are in the
[ERPNext workflow benchmark](docs/erpnext-workflow-benchmark-results.md).

## Review and workflow checks

The tested workflow showed that:

- provider-backed processing stopped at `needs_review`, even for a clean, high-confidence invoice;
- explicit reviewer approval was required before the invoice became `approved`;
- the duplicate copy received `duplicate_invoice` while the original remained reviewable;
- clean decisions and correction-required cases appeared in separate queue states;
- the duplicate reason appeared beside the PDF;
- the UI disabled approval for blocked invoices and the backend refused the same request;
- approved, rejected, and exported invoices could not be edited through the draft API;
- correction requests returned the invoice to the uploader and kept the original extraction,
  before/after values, actor, reason, timestamp, and field-level diff;
- the provider-backed workflow recorded six audit events.

## Engineering checks

The recorded clean release passed its backend coverage gate with at least **91.21% line coverage**.
Supporting evidence records **521 backend tests**, **23 frontend tests**, **29 fixture-browser
tests**, and **one browser journey against the local full stack**. Formatting, lint, type,
dependency, complexity, production-build, and packaging checks are part of the same release path.

## How this was verified

| Evidence                                                                    | Recorded result                                                                        | Tested revision                                             | Limitation                                                |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------- |
| [Sealed holdout JSON](docs/evidence/external-invoice-v2-holdout-final.json) | 79/80 fields; 100% validation and blocker match                                        | Critical-code hash `0c1fa3d...`; run records dirty worktree | Licensed synthetic data; one unsupported due date         |
| [External evaluation summary](docs/external-invoice-evaluation-v2.md)       | All predeclared holdout gates passed                                                   | Experiment `20260720T043136Z`                               | Not customer traffic or production accuracy               |
| [Release verification JSON](docs/evidence/release-verification.json)        | Coverage gate plus 521 backend, 23 frontend, 29 fixture-browser, and 1 full-stack test | Clean source `8b36ba5...`                                   | Local Windows release; no independent security assessment |
| [Evaluation log](docs/evaluation-experiment-log.md)                         | Failed and successful diagnostics retained                                             | Each run records its own commit and fingerprints            | Provider behavior and cost can change                     |

## Failure handling

| Failure                              | System response                                                      |
| ------------------------------------ | -------------------------------------------------------------------- |
| Missing or ambiguous field           | Keep the value empty or request a correction. Do not guess silently. |
| Arithmetic mismatch                  | Show the validation error and block approval.                        |
| Duplicate invoice                    | Block the copy and keep the original reviewable.                     |
| Invalid provider credential          | Stop without retrying and report provider health.                    |
| Rate limit or retryable server error | Retry within a fixed limit, then move the job to the failed queue.   |
| Export delivery failure              | Keep the approved state and record the failed attempt for retry.     |
| Invalid role or workspace            | Refuse the request at the API.                                       |

## Main architecture decision

The architecture separates proposal, validation, and decision:

```text
AI proposes invoice data.
Application rules validate the proposal.
A human approves, rejects, or requests a correction.
```

This design keeps the risky parts visible and testable. The model can suggest data, but it cannot
approve or export an invoice.

## Limitations

- All benchmark invoices are synthetic.
- The external FATURA packs are licensed synthetic documents, not customer traffic.
- Provider availability interrupted the first external holdout. The second still produced one
  unsupported due date.
- No finance user has completed the planned usability study.
- Workflow time was measured only in a single-operator local pilot; production savings, cost
  savings, and customer impact have not been measured.
- Provider behavior may change when hosted models change.
- Invoice is the only complete document schema.
- Local authentication, SQLite, and file storage are not a production tenancy setup.
- ERPNext delivery has been verified against a local draft-only sandbox, not a production ERP.

## Next steps

1. Run the documented usability study with 3–5 finance users and fix the task failures it reveals.
2. Validate a small set of legally usable real invoices without committing the raw documents.
3. Replace seeded role tokens with production identity and tenant membership.
4. Add a production malware scanner, managed object storage, retention rules, backups, and an
   independent security review.
5. Add worker heartbeat telemetry and a managed queue before making any distributed-scale claim.
