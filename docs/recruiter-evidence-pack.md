# Recruiter Evidence Pack

This page is the shortest defensible path through the project. It separates implemented behavior
from benchmark evidence and from work that still requires real users or production infrastructure.

## The Problem

Invoice reviewers must compare a source PDF with extracted data, resolve inconsistencies, and keep
an auditable decision before approved data moves downstream. The expensive failure is not merely a
bad OCR field; it is an unsafe approval or export based on that field.

## What The System Demonstrates

| Claim                                            | Direct evidence                                                                                                               | What it does not prove                                     |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| AI output is not treated as authority.           | Error-level validation blocks approval in both the API and UI.                                                                | That every possible invoice risk has a rule.               |
| Reviewers can verify where a value came from.    | Field controls expose AI confidence, OCR excerpt, and source page; corrections show human provenance and before/after values. | Bounding-box-level OCR highlighting for every provider.    |
| Human decisions are consequential and auditable. | Approval, rejection, correction, actor, reason, and timestamp are persisted.                                                  | Cryptographic tamper evidence or regulatory certification. |
| Export is controlled.                            | Only approved invoices are eligible; execution is idempotent and failure-aware.                                               | A production ERP deployment.                               |
| The application is connected end to end.         | One real browser journey runs React, FastAPI, SQLite, the worker, correction, approval, and export.                           | Hosted availability or multi-tenant scale.                 |
| Extraction quality is measured.                  | Versioned synthetic and licensed-synthetic evaluations retain failures, fingerprints, cost, and latency.                      | Production accuracy on customer invoices.                  |
| Role boundaries are server-enforced.             | Negative API tests deny uploader and reviewer access to administrator surfaces.                                               | Production identity lifecycle or tenant administration.    |

## Sixty-Second Review Path

1. Start with the [review workspace screenshot](assets/screenshots/review.png) or the
   [captioned demo](assets/demo/invoice-review-demo.mp4).
2. Read the [case study](../PORTFOLIO_CASE_STUDY.md) for the business and design decisions.
3. Inspect the [architecture](../ARCHITECTURE.md) for authority and data boundaries.
4. Check the [scenario coverage matrix](../SCENARIO_COVERAGE_MATRIX.md) and
   [evaluation log](evaluation-experiment-log.md).
5. Inspect [release verification](evidence/release-verification.json) for the latest local gate.
6. Read the [security posture](security/SECURITY_POSTURE.md) before interpreting the project as
   deployable software.

## Representative Business Cases

| Case                                | Expected consequence                                                    |
| ----------------------------------- | ----------------------------------------------------------------------- |
| Clean invoice                       | Wait for an explicit reviewer decision; never auto-approve.             |
| Missing required value              | Explain the blocker and request correction.                             |
| Subtotal, tax, and total mismatch   | Block approval until the values are corrected.                          |
| Duplicate vendor and invoice number | Block the copy while preserving the original record.                    |
| Reviewer correction                 | Preserve original AI value, before/after diff, actor, reason, and time. |
| Approved invoice                    | Become export-eligible but do not execute a payment.                    |
| Failed export                       | Preserve approval and expose a retryable delivery failure.              |

## Current Evidence Boundary

- The committed 20-document set is deterministic and synthetic.
- The external FATURA packs are licensed synthetic documents, not customer traffic.
- No formal finance-user usability study or business-impact measurement has been completed.
- Local SQLite, local sessions, and seeded role tokens are portfolio boundaries, not production
  tenancy.
- Hosted processing of untrusted or real client documents remains blocked by the security posture.

The strongest accurate positioning is:

> An AI document operations system that combines evidence-grounded extraction, deterministic
> validation, human approval, controlled export, and reproducible evaluation.
