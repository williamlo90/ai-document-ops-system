# Recruiter Demo Script - 3 to 5 Minutes

Recorded artifact: [captioned MP4](assets/demo/ai-document-ops-demo.mp4).

The committed recording uses the real React pages, PDF viewer, and a deterministic route-level
contract harness. Provider-backed accuracy and latency evidence remain separate benchmark claims.

## 0:00 - 0:20: Claim Boundary

Say:

> Finance reviewers need to compare the source invoice with extracted data, catch exceptions, and
> record a decision. AI reads the document, deterministic code enforces safety rules, and a human
> owns approval.

## 0:20 - 0:50: Overview

Show urgent work, grounded findings, the decision queue, throughput, and recent decisions. Explain
that every aggregate links to the workflow that defines it.

## 0:50 - 1:20: Invoices and Review Queue

1. Open Invoices and inspect the selected PDF, owner, status, and validation findings.
2. Open Review Queue and show risk, confidence, age, owner, and the plain-language finding.
3. Explain that upload and reviewer authority are separate roles.

## 1:20 - 2:00: Review and Blocker

1. Open the Invoice Review workspace.
2. Compare the real synthetic PDF with extracted fields and line items.
3. Show the missing-PO validation blocker and disabled approval.
4. State that the backend refuses the unsafe transition independently of the button.

## 2:00 - 2:35: Exception and Correction Loop

1. Open Exceptions and reconcile the summary, table, and selected issue.
2. Show what happened, what is required, and the related blocked check.
3. Switch to the uploader correction state and show the reviewer note, editable fields, and required
   explanation.

## 2:35 - 3:05: Recorded Decision and Export

1. Return to the corrected, revalidated invoice after approval.
2. Show actor, timestamp, audit-event count, and export eligibility.
3. Open Exports and show approved-only membership, eligibility checks, idempotent execution, run
   history, and retry-safe failure evidence.

## 3:05 - 3:35: Evaluation and System

1. Show the synthetic evidence badge, quality gates, field results, scenario coverage, estimated
   provider cost, and visible limitations.
2. Show System and explain that one degraded export capability does not make healthy intake,
   reading, extraction, review, or storage appear unavailable.

## Close

Say:

> This proves a production-shaped invoice workflow with explicit safety boundaries and
> reproducible engineering evidence. It does not prove production accuracy, customer impact, or a
> hosted finance platform.

## Recording Checklist

- the PDF is visible and agrees with the displayed invoice fields
- no API key, private document, local path, or browser extension appears
- approval remains human-controlled and a validation blocker remains enforced
- correction lineage and post-decision audit consequence are visible
- synthetic and customer-validation limitations are stated
- final video remains between 3 and 5 minutes
