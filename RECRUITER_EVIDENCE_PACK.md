# Recruiter Evidence Pack

## 60-Second Summary

Finance operations reviewers need to verify invoice data without allowing uncertain extraction
or a business-rule failure to become an approval. This project demonstrates a bounded workflow:

```text
PDF upload -> AI-assisted reading -> deterministic checks -> human decision -> audit record
```

The system uses AI to read documents, deterministic code to enforce policy, and a reviewer to
make the consequential decision. It is a local portfolio release candidate, not a production
finance platform.

## What This Project Proves

| Claim | Repository evidence |
| --- | --- |
| A reviewer can compare the source PDF with extracted fields. | [Reviewer screenshot](docs/assets/screenshots/reviewer-decision.png), [UI evidence matrix](docs/ui-release-evidence.md), and [captioned demo](docs/assets/demo/ai-document-ops-demo.mp4) |
| Extraction confidence cannot approve an invoice. | Approval remains an explicit reviewer action in the UI and backend decision service. |
| Business-rule failures block approval. | Total, date, currency, required-field, and duplicate cases are covered in the [scenario matrix](SCENARIO_COVERAGE_MATRIX.md) and automated tests. |
| Reviewer corrections become auditable data, not chat history. | [Reviewer correction feedback](docs/reviewer-correction-feedback.md) records before/after diffs, original AI snapshots, reason lineage, and privacy-filtered aggregate evidence. |
| A decision leaves inspectable consequences. | The [post-approval screenshot](docs/assets/screenshots/approved-decision.png) shows decision status, actor, timestamp, audit-event count, and export eligibility. |
| Provider behavior was tested beyond one clean sample. | The [scenario evidence](docs/invoice-scenarios-v1-evidence.md) records three real-provider iterations across 20 committed synthetic PDFs. |
| External behavior was tested and not overclaimed. | [V1](docs/external-invoice-evaluation-v1.md) preserves a provider failure; the non-overlapping [V2 sealed holdout](docs/external-invoice-evaluation-v2.md) completed 10 / 10 documents with 98.75% field accuracy and one documented hallucination. |
| The artifact is reproducible and bounded. | The [runbook](RUNBOOK.md), automated quality gates, public-artifact checks, and explicit limitations define the supported local profile. |

## Responsibility Boundary

| Layer | Allowed responsibility | Not allowed |
| --- | --- | --- |
| OCR and extraction providers | Read text and propose structured invoice fields with source evidence. | Approve, reject, export, or invent a missing value. |
| Deterministic application code | Validate required fields, arithmetic, dates, currency, duplicates, roles, states, and export eligibility. | Override a reviewer decision or claim semantic certainty. |
| Human reviewer | Compare the PDF with extracted data and approve, reject, or request correction. | Bypass backend blockers or rewrite terminal decision evidence. |

## Observed Evidence

| Evidence | Observed result | Boundary |
| --- | --- | --- |
| Synthetic scenario set | 20 deterministic invoice PDFs across normal, missing-field, validation, duplicate, OCR, and layout cases. | Synthetic fixtures are not customer data. |
| Final provider-backed regression | 160 / 160 evaluated fields and 20 / 20 expected validation outcomes. | This is a small golden-set result, not production accuracy. |
| Static validation blockers | Seven fixtures correctly required follow-up: three missing critical fields and four deterministic business-rule failures. | These rules cover the committed invoice contract only. |
| Stateful duplicate control | The first invoice remained clear; the second matching vendor and invoice number received `duplicate_invoice` and approval was blocked. | Duplicate detection is workspace-scoped and depends on stored application state. |
| Approval audit consequence | A completed local approval recorded actor, timestamp, terminal status, export eligibility, and six audit events. | Export eligibility is not a claim that an ERP delivery occurred. |
| Reviewer correction feedback | Six deterministic feedback-lineage checks passed and public summaries exclude document IDs, actors, reasons, and values. | This proves correction capture and privacy filtering, not model improvement or user adoption. |
| External licensed holdout | The V2 sealed holdout completed 10 / 10 documents with 98.75% field accuracy, 100% validation match, and one unsupported due date. | This is bounded licensed-synthetic evidence, not customer or production accuracy. |
| Automated verification | 453 backend tests passed with 2 skipped; 13 frontend tests passed; Ruff, lint, production build, and dependency audits passed. | Tests support the local repository contract, not hosted production readiness. |
| Recruiter demo | A captioned 3:53 walkthrough covers the business UI, blocker, correction loop, recorded decision, export, evaluation, and system evidence. | The video uses a committed synthetic PDF and deterministic UI contract harness. |

The current provider-backed evaluation used Mistral OCR and an OpenAI structured extraction model.
The demo harness is intentionally deterministic so the same short narrative can be
reviewed without credentials or provider drift. These are separate evidence types and are not
presented as the same run.

## Why It Matters To Finance Operations

This project addresses a plausible operational risk: extracted invoice data can look convincing
while still being incomplete, inconsistent, or duplicated. The demonstrated controls make the
review boundary visible and prevent the UI from treating AI confidence as business authority.

No time saving, cost saving, false-approval reduction, or customer outcome has been measured.
Those claims require external users and representative business data.

## What This Does Not Prove

- production accuracy across vendors, languages, scans, and invoice templates
- customer adoption or improvement over a measured manual baseline
- hosted multi-tenant security, managed identity, backups, or operational monitoring
- live accounting or ERP delivery
- support for document types other than invoices
- autonomous finance operations
- production provider availability or an operational SLA

## Evidence Index

- [Portfolio case study](PORTFOLIO_CASE_STUDY.md)
- [Scenario coverage matrix](SCENARIO_COVERAGE_MATRIX.md)
- [Provider-backed scenario evidence](docs/invoice-scenarios-v1-evidence.md)
- [External invoice evaluation V2](docs/external-invoice-evaluation-v2.md)
- [Evaluation experiment log](docs/evaluation-experiment-log.md)
- [External invoice evaluation V1](docs/external-invoice-evaluation-v1.md)
- [Reviewer correction feedback](docs/reviewer-correction-feedback.md)
- [Reliability report](docs/reliability-report.md)
- [Architecture and decision boundaries](ARCHITECTURE.md)
- [Demo notes and reproduction](docs/demo-video.md)
- [UI release evidence](docs/ui-release-evidence.md)
- [Roadmap and remaining release work](ROADMAP.md)
