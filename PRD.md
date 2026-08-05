# Product Requirements - AI-Powered Invoice Review & Approval System

## Problem

Invoice review is risky when extracted data, source evidence, validation findings, and reviewer
decisions live in separate places. A reviewer needs one clear workflow for comparing the source
PDF with structured data, resolving exceptions, and recording a review decision with a clear audit
trail.

This product addresses that review workflow. It does not attempt to replace finance staff or
automate payment execution.

## Users

### Invoice uploader

- uploads a PDF
- sees whether reading is in progress, needs correction, awaits review, or is complete
- opens the invoice and checks its current status

### Finance reviewer

- sees invoices waiting for a decision separately from invoices needing correction
- compares the source PDF with extracted fields
- understands validation blockers in business language
- approves, rejects, or asks for correction

### Technical evaluator

- inspects provider status, scenario results, audit events, and run traces outside the primary
  business workflow

## Core Journey

```text
Upload invoice
-> Read PDF
-> Extract structured fields
-> Apply deterministic validation
-> Route to reviewer or correction
-> Record reviewer decision
-> Allow controlled export only after approval
```

## Functional Requirements

### Intake and processing

- accept PDF invoices within the configured size limit
- store source documents privately
- expose explicit processing, retry, and terminal states
- never infer successful processing from a frontend timer

### Evidence and validation

- display the PDF beside editable extracted fields
- retain source evidence and field confidence where available
- validate required fields, arithmetic consistency, supported values, and duplicates
- treat missing or ambiguous information as a correction case instead of silently guessing

### Review and decisions

- require an explicit reviewer action for approval
- keep approve, reject, and correction behavior distinct
- prevent approval while error-level validation issues remain
- prevent edits to an already approved, rejected, or exported invoice
- preserve role and workspace boundaries in the API

### Audit and execution

- record upload, processing, validation, correction, and decision events
- allow export only from an approved state
- retain an approved state when an external delivery fails so it can be retried safely
- keep outbound adapters isolated from raw PDF bytes and credentials

### Technical evidence

- provide deterministic scenario fixtures and evaluation output
- preserve provider error classification and retry evidence
- expose technical traces without making them required for normal invoice review

## Non-Functional Requirements

- local-first setup with credential-free mock providers
- responsive uploader and reviewer flows on desktop and mobile
- clear loading, empty, blocked, and error states
- security headers, rate limiting, CSRF origin checks, and protected API routes
- repository hygiene that excludes credentials, uploads, databases, caches, and build output
- automated backend, frontend, lint, build, and public-artifact gates

## Success Criteria

- a first-time user can upload an invoice and identify its next state without documentation
- a reviewer can identify the source PDF, extracted values, blocking reason, and available
  decision from one screen
- high-confidence extraction cannot bypass human approval
- invalid state transitions and unresolved blockers are refused by the backend
- a technical evaluator can reproduce tests and the synthetic scenario benchmark
- public claims remain within observed evidence

## Out Of Scope

- payment or bank-transfer execution
- unrestricted autonomous action
- complete support for non-invoice documents
- production multi-tenancy, billing, backups, and monitoring
- claims based on customer data, business impact, or statistically representative accuracy

## Product Claim

> An invoice-review workflow with source-linked extraction, deterministic validation,
> explicit human decisions, and approval-gated export.
