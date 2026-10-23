# AI-Powered Invoice Review & Approval System - Project Tour

This short tour covers the working product, its strongest recorded evidence, and the gaps that
remain.

## One-minute review path

1. See the [review workspace](assets/screenshots/review.png) or watch the
   [captioned demo](assets/demo/invoice-review-demo.mp4).
2. Check the [sealed holdout artifact](evidence/external-invoice-v2-holdout-final.json) and
   [external evaluation summary](external-invoice-evaluation-v2.md).
3. Check the [recorded clean release](evidence/release-verification.json) and the retained
   [failed diagnostic](evidence/current-provider-diagnostic.failed-20260728T080824Z.json).
4. Review the [ERPNext technical verification](erpnext-phase7-verification.md) for the controlled
   draft-delivery boundary and the [paired timing result](erpnext-paired-draft-timing-results.md)
   for the six-case workflow comparison.
5. Read the [evaluation log](evaluation-experiment-log.md) for the experiment chronology.

## Evidence summary

| Claim                            |                                                                 Result | Scope                                                          | Exact evidence                                                  |
| -------------------------------- | ---------------------------------------------------------------------: | -------------------------------------------------------------- | --------------------------------------------------------------- |
| Exact field match                |                                                     **98.75% (79/80)** | Sealed 10-invoice licensed-synthetic holdout                   | [Holdout JSON](evidence/external-invoice-v2-holdout-final.json) |
| Validation and approval controls |                                                        **100% / 100%** | Validation-code and approval-blocker match on the same holdout | [Holdout JSON](evidence/external-invoice-v2-holdout-final.json) |
| Backend coverage                 |                                              **At least 91.21% lines** | Recorded clean local release source; coverage gate passed      | [Release JSON](evidence/release-verification.json)              |
| Engineering verification         | **521 backend, 23 frontend, 29 fixture-browser, 1 full-stack journey** | Clean local release on the recorded Windows environment        | [Release JSON](evidence/release-verification.json)              |
| Known extraction failure         |                                             **1 unsupported due date** | Same sealed holdout; no blocker mismatch                       | [Evaluation summary](external-invoice-evaluation-v2.md)         |
| ERPNext delivery boundary        |                                               **Approved drafts only** | Local sandbox; no submit, post, payment, cancel, or delete     | [Technical verification](erpnext-phase7-verification.md)        |
| ERPNext paired draft timing      |                                   **153s to 49s median (68.0% lower)** | Six draft-eligible cases; one operator; local sandbox          | [Timing result](erpnext-paired-draft-timing-results.md)         |
| ERPNext recorded outcomes        |                                        **10/10 assisted; 9/10 manual** | Six corrected draft reruns plus four retained blocker outcomes | [Timing result](erpnext-paired-draft-timing-results.md)         |

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
| Export is controlled.                                | Only approved invoices are eligible. ERPNext delivery is idempotent and draft-only.                 | A production ERP connection and accounting sign-off.       |
| The main workflow is connected end to end.           | A browser test runs React, FastAPI, SQLite, the worker, correction, approval, and export.           | Hosted availability and multi-tenant scale.                |
| Extraction quality is measured.                      | Synthetic evaluations retain results, failures, fingerprints, cost, and latency.                    | Production accuracy on customer invoices.                  |
| Roles are enforced by the server.                    | Negative API tests deny uploader and reviewer access to administrator routes.                       | Production identity and tenant administration.             |

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
- No formal finance-user usability study or production business-impact measurement has been
  completed. Workflow timing covers one operator and six known synthetic draft cases; the 10-case
  outcome record includes four retained blocker observations.
- SQLite, local sessions, and seeded role tokens are part of the portfolio setup, not a production
  tenancy model.
- Processing untrusted or real client documents still requires the security work listed in the
  security posture.

## Project summary

The workflow reads invoices and validates extracted data while leaving approval to a human
reviewer. Export remains controlled, and the evaluation record keeps enough detail to reproduce
each result.
