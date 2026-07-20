# Portfolio Case Study - Safer Invoice Review

## Executive Summary

Finance operations reviewers need to compare invoice PDFs with extracted data, catch exceptions,
and record decisions before approved data can move downstream. The failure cost is asymmetric: a
missing field should slow the workflow down, while an incorrect approval can propagate bad data.

AI Document Operations System is a local-first portfolio implementation of that control point. It
uses AI for document reading, deterministic code for business safeguards, and a human reviewer for
consequential decisions.

## User and Constraint

Primary user: a finance operations reviewer or accounts-payable operator handling incoming
invoices.

Operational constraint: OCR and language models are probabilistic. The product must remain useful
when extraction is incomplete, ambiguous, or wrong. Therefore uncertainty is surfaced for review
instead of hidden behind an automatic approval.

## Baseline Workflow

Without a shared review surface, a reviewer typically needs to:

1. open the source PDF
2. copy or compare invoice fields manually
3. calculate or inspect totals
4. decide whether missing or inconsistent values require follow-up
5. communicate the result
6. preserve evidence of the decision

This case study does not claim a measured time reduction because no real user study has been run.
The design target is narrower: put the PDF, structured fields, validation reasons, and permitted
decision in one workflow.

## Implemented Workflow

```text
Uploader submits invoice
-> OCR provider reads pages
-> extractor returns grounded invoice fields
-> deterministic rules validate fields and totals
-> clean case waits for reviewer decision
-> blocked case requests correction
-> reviewer compares source PDF and data
-> decision and audit events are persisted
-> approved state unlocks controlled export
```

## What AI Does

- converts invoice pages into machine-readable text
- maps evidence into the invoice schema
- provides confidence and source context when available

The extraction prompt forbids guessing missing values. A deterministic grounding guard rejects an
ambiguous seller name even if the model returns one.

## What Deterministic Code Does

- enforces required fields and normalization
- checks subtotal, tax, total, and line-item consistency
- detects duplicate vendor and invoice-number pairs within a workspace
- controls processing retries and terminal states
- enforces roles, workspaces, and valid status transitions
- blocks approval while error-level validation findings remain
- blocks export until a reviewer has approved the invoice

## What the Human Controls

- verifies extracted values against the visible PDF
- corrects data before submission when evidence supports the change
- approves a clean invoice
- rejects an invalid invoice
- asks for correction when evidence is missing or inconsistent

Model confidence never replaces this authority.

## Representative Scenarios

The versioned synthetic dataset contains 20 PDFs covering:

- ordinary single-page invoices
- intentionally missing vendor, date, or tax fields
- total and line-item inconsistencies
- a duplicate invoice pair
- unsupported or unusual values
- low-contrast text
- rotated content
- a multi-page invoice

The first provider-backed run exposed three unsafe false fills in intentionally missing fields.
Prompt-level null rules corrected two. A deterministic seller-context guard corrected the final
vendor error. The final controlled run matched 160 of 160 evaluated fields and all 20 expected
validation outcomes, with no provider error and 1.09 seconds average observed provider latency.

These numbers describe one small synthetic golden set. They are not production accuracy,
throughput, or SLA claims.

Two separate 25-document licensed synthetic FATURA packs were prepared outside Git. The first
sealed holdout exposed a provider-availability failure: only 1 of 10 documents completed both
providers. That negative result remains in the evidence record. A second pack used 25 previously
unseen source layouts and a new sealed holdout. With Mistral OCR and OpenAI extraction, all 10
holdout documents completed, field accuracy was 98.75%, and validation and approval-blocker
accuracy were 100%. One unsupported due date was still hallucinated and remains documented.

## Safety Evidence

- real-provider processing stopped at `needs_review`, including for a clean high-confidence invoice
- explicit approval was required before the state became `approved`
- the duplicate copy received `duplicate_invoice` while the original remained clear
- the queue separated clean decisions from correction-required cases
- the duplicate reason was visible beside the source PDF
- the UI disabled approval and the backend independently refused it
- approved, rejected, and exported invoice data could not be silently edited through the draft API
- correction requests returned ownership to the uploader and preserved original AI output,
  before/after values, actor, reason, timestamp, and field-level diff
- the tested provider-backed workflow produced six durable audit events

## Engineering Evidence

- 432 backend tests passed with 2 environment-dependent tests skipped
- 13 frontend tests passed
- frontend lint and production build passed
- backend Ruff checks passed
- production dependency audit reported no known npm vulnerability at verification time
- security tests cover session, role, workspace, CSRF, headers, upload, and state-transition boundaries
- public artifact tests prevent `.env`, local databases, uploads, caches, and build output from being packaged

## Failure Modes and Product Response

| Failure mode | Product response |
| --- | --- |
| Missing or ambiguous field | Preserve null or route to correction; do not silently guess. |
| Arithmetic mismatch | Show a validation reason and block approval. |
| Duplicate invoice | Mark the copy for correction and keep the original reviewable. |
| Invalid provider credential | Fail as non-retryable and expose provider health. |
| Rate limit or supported server failure | Use bounded retry and dead-letter behavior. |
| Export delivery failure | Keep the approved state and record the failed attempt for safe retry. |
| Cross-workspace or invalid-role action | Refuse at the API boundary. |

## Architecture Decision

The main design decision is separation of authority:

```text
AI proposes structured evidence.
Deterministic code decides whether the state is safe to review or execute.
A human makes the consequential business decision.
```

This produces a more defensible portfolio claim than unrestricted automation because every risky
boundary can be demonstrated and tested.

## Limitations and Next Evidence

- all benchmark invoices are synthetic
- the external FATURA packs are licensed synthetic evidence, not customer traffic; V1 preserved a
  provider failure and V2 still produced one unsupported due date
- no finance operations user has completed a formal usability study
- no customer baseline, time saving, cost saving, or error reduction has been measured
- provider behavior may change as hosted models change
- invoice is the only end-to-end document schema
- local authentication, SQLite, and file storage are not a production tenancy architecture
- the ERP/accounting integration remains a controlled mock or CSV boundary

The next valuable validation is a small, permissioned real-world invoice set plus observed reviewer
tasks. That evidence should precede another document type or broader automation claim.
