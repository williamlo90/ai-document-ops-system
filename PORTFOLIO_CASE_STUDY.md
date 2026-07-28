# Portfolio Case Study — Safer Invoice Review

## Summary

Finance reviewers need to compare invoice PDFs with extracted data, catch incorrect or missing
values, and record a decision before approved data moves downstream. A missing field can slow the
workflow down. An incorrect approval can send bad data into an accounting process.

I built Invoice Review to keep the PDF, extracted fields, validation results, and reviewer decision
in one workflow. AI reads the document and proposes structured data. Application rules check that
data. A human reviewer makes the final decision.

## My role

I built this as a solo portfolio project from 12–28 July 2026 and remain its only contributor.

I was responsible for:

- product scope;
- architecture and implementation direction;
- evaluation design;
- failure analysis;
- documentation;
- release checks.

The project originally covered a broad document-operations platform. Repeated UI reviews showed
that the workflow-engine concepts made ordinary invoice review harder to understand, so I narrowed
the product to one complete invoice journey.

I made several decisions during that process:

- keep invoice as the only complete document type instead of adding a shallow second workflow;
- never approve an invoice from model confidence alone;
- place the PDF beside editable fields and validation errors;
- retain the original extraction when a reviewer changes a value;
- keep evaluation, provider cost, and operational details under administrator navigation;
- keep existing internal API names because renaming them would add migration risk without changing
  product behavior.

I also rejected a chatbot, unrestricted autonomous actions, payment execution, and production
integrations. None of those additions would improve the core review workflow at its current stage.

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

I have not measured this workflow against a manual baseline. For now, the goal is simple: keep the
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

## Evaluation cases

The committed dataset contains 20 synthetic PDFs:

- ordinary single-page invoices;
- invoices with a missing vendor, date, or tax value;
- total and line-item mismatches;
- a duplicate invoice pair;
- unsupported or unusual values;
- low-contrast text;
- rotated content;
- one multi-page invoice.

The first provider-backed run filled three fields that were intentionally missing. Stronger null
instructions corrected the date and tax errors. A deterministic seller-context check rejected the
remaining vendor error.

A later clean-commit diagnostic found a different problem. The model returned a localized amount
such as `1.250,00`, but the decimal parser rejected it. I kept the failed 19-of-20 run, added
deterministic normalization and a regression test, and ran the same diagnostic again.

The passing run:

- processed all 20 invoices;
- matched 160 of 160 expected fields;
- matched all validation outcomes;
- matched all approval-blocker outcomes;
- recorded source information for 87.1% of correct non-null fields;
- made 40 provider calls;
- averaged 3.69 seconds per invoice;
- produced a dated list-price estimate of $0.129488.

This is a small synthetic diagnostic set. The result is useful for regression testing, but it is
not a production accuracy or throughput estimate.

## External synthetic holdout

I also prepared two licensed 25-document FATURA packs outside Git.

The first sealed holdout exposed a provider-availability problem: only 1 of 10 selected documents
completed both provider steps. I kept that failed result.

The second pack used 25 source layouts that had not appeared in the first pack. After the diagnostic
fixes were frozen, I ran one new sealed 10-document holdout with Mistral OCR and OpenAI extraction.
All 10 documents completed.

The result was:

- 98.75% field match;
- 100% validation match;
- 100% approval-blocker match.

One due date was not supported by the source document but was still generated by the model. That
failure remains documented. The holdout is licensed synthetic data, not customer traffic.

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

- The release record contains the backend, frontend, fixture-browser, and real full-stack browser
  test counts from a clean commit.
- Frontend formatting, lint, tests, and production build are part of the release command.
- Backend formatting, lint, complexity, dependency, and test checks run in the same command.
- The frontend dependency check fails on unreviewed high or critical findings. One React Router
  advisory that does not apply to this client-only Vite setup has a documented expiration date.
- Security tests cover sessions, roles, workspaces, CSRF, headers, uploads, and state transitions.
- Packaging tests prevent `.env`, local databases, uploaded files, caches, and build output from
  entering the public artifact.

The exact counts and environment are recorded in
[release verification](docs/evidence/release-verification.json).

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

I separated proposal, validation, and decision:

```text
AI proposes invoice data.
Application rules validate the proposal.
A human approves, rejects, or requests a correction.
```

I chose this design because the risky parts are visible and testable. The model can suggest data,
but it cannot approve or export an invoice.

## Limitations

- All benchmark invoices are synthetic.
- The external FATURA packs are licensed synthetic documents, not customer traffic.
- The first external holdout kept a provider failure. The second still produced one unsupported due
  date.
- No finance user has completed the planned usability study.
- I have not measured reviewer time savings, cost savings, or error reduction.
- Provider behavior may change when hosted models change.
- Invoice is the only complete document schema.
- Local authentication, SQLite, and file storage are not a production tenancy setup.
- ERP delivery remains a mock or CSV integration.

## What I would do next

1. Run the documented usability study with 3–5 finance users and fix the task failures I observe.
2. Validate a small set of legally usable real invoices without committing the raw documents.
3. Replace seeded role tokens with production identity and tenant membership.
4. Add a production malware scanner, managed object storage, retention rules, backups, and an
   independent security review.
5. Add worker heartbeat telemetry and a managed queue before making any distributed-scale claim.
