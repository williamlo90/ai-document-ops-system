# AI-Powered Invoice Review & Approval System - Project Tour

This short tour covers the working product, the evaluation record, and the gaps that remain.

## The problem

Invoice reviewers need to compare a source PDF with extracted data, resolve inconsistencies, and
record a decision before approved data moves downstream. A wrong OCR field can lead to an incorrect
approval or export, so the model is not allowed to make that decision.

## What the project shows

| What it shows                                        | Where to verify it                                                                                  | What is still missing                                      |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| AI output is treated as a proposal, not an approval. | Validation errors block approval in both the API and UI.                                            | Coverage of every possible invoice risk.                   |
| Reviewers can check where a value came from.         | Fields show confidence, OCR excerpts, and source pages. Corrections show human before/after values. | Bounding-box highlighting for every OCR provider.          |
| Review decisions are recorded.                       | Approval, rejection, correction, actor, reason, and timestamp are persisted.                        | Cryptographic tamper evidence or regulatory certification. |
| Export is controlled.                                | Only approved invoices are eligible. Delivery is idempotent and records failures.                   | A production ERP connection.                               |
| The main workflow is connected end to end.           | A browser test runs React, FastAPI, SQLite, the worker, correction, approval, and export.           | Hosted availability and multi-tenant scale.                |
| Extraction quality is measured.                      | Synthetic evaluations retain results, failures, fingerprints, cost, and latency.                    | Production accuracy on customer invoices.                  |
| Roles are enforced by the server.                    | Negative API tests deny uploader and reviewer access to administrator routes.                       | Production identity and tenant administration.             |

## One-minute review path

1. Open the [review workspace screenshot](assets/screenshots/review.png) or watch the
   [captioned demo](assets/demo/invoice-review-demo.mp4).
2. Read the [case study](../PORTFOLIO_CASE_STUDY.md) for the problem, design choices, and results.
3. Check the [architecture](../ARCHITECTURE.md) for the main components and decision flow.
4. Review the [scenario matrix](../SCENARIO_COVERAGE_MATRIX.md) and
   [evaluation log](evaluation-experiment-log.md).
5. Inspect the [current provider diagnostic](evidence/current-provider-diagnostic.json) and
   [release verification](evidence/release-verification.json).
6. Read the [security posture](security/SECURITY_POSTURE.md) before considering any deployment with
   real invoices.

## Representative cases

| Case                                | Expected behavior                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| Clean invoice                       | Wait for an explicit reviewer decision. Never auto-approve.                  |
| Missing required value              | Explain the blocker and request a correction.                                |
| Subtotal, tax, or total mismatch    | Block approval until the values are corrected.                               |
| Duplicate vendor and invoice number | Block the copy while keeping the original reviewable.                        |
| Reviewer correction                 | Keep the original AI value, before/after diff, actor, reason, and timestamp. |
| Approved invoice                    | Make it export-eligible without executing a payment.                         |
| Failed export                       | Keep the approval and record a retryable delivery failure.                   |

## Current limitations

- The committed 20-document dataset is deterministic and synthetic.
- The external FATURA packs are licensed synthetic documents, not customer traffic.
- No formal finance-user usability study or business-impact measurement has been completed.
- SQLite, local sessions, and seeded role tokens are part of the portfolio setup, not a production
  tenancy model.
- Processing untrusted or real client documents still requires the security work listed in the
  security posture.

## Project summary

The workflow reads invoices and validates extracted data while leaving approval to a human
reviewer. Export remains controlled, and the evaluation record keeps enough detail to reproduce
each result.
