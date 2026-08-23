# ERPNext Integration and Benchmark SDLC

Status: Phase 11 complete
Last updated: 2026-08-22

This plan governs the ERPNext draft integration and its controlled time benchmark. It uses the
fixed 10-invoice `T01`-`T10` synthetic set selected in Codex task
`019fd72c-a003-77d0-bfcf-57313c964d32`. It does not create or select a new dataset.

## Locked Scope

- Target system: ERPNext running locally or in an isolated sandbox.
- Target document: ERPNext Purchase Invoice in Draft state (`docstatus = 0`).
- The application may create and verify a draft. It must never submit, post, pay, or otherwise
  finalize an accounting transaction automatically.
- Only an invoice with an explicit human approval may be sent to ERPNext.
- Private benchmark copies, timing records, credentials, and ERP databases remain outside Git. The
  source documents are existing synthetic fixtures under `examples/benchmark`.
- The fixed 10-invoice pack is identified by fingerprint
  `ca37538cd0f823acf811f23b92ffcda9e74c56000ed7f580def37bee75420407`.
- These invoices may support a controlled workflow-time comparison. Because they have already been
  evaluated, they must not be presented as a new blind extraction holdout.

## Compared Workflows

```text
Manual
PDF opened -> operator enters values directly in ERPNext -> draft saved -> draft verified

Application-assisted
PDF uploaded -> extraction reviewed -> human approves -> application creates ERPNext draft
-> draft verified
```

The benchmark compares the complete workflows. A spreadsheet records timing and outcomes only; it
is not an intermediate source for ERP data entry.

## SDLC Checklist

### Phase 1 - Requirements and Scope

- [x] Select ERPNext as the local or sandbox ERP.
- [x] Restrict the integration to draft Purchase Invoices.
- [x] Prohibit automatic submit, posting, and payment.
- [x] Reuse exactly the fixed `T01`-`T10` synthetic set selected by the user.
- [x] Define the manual and application-assisted workflows.
- [x] Keep private documents, labels, databases, and secrets outside Git.
- [x] Limit the final claim to a controlled, single-operator benchmark.

Exit criterion: product boundary, dataset identity, compared workflows, and claim boundary are
written and no longer ambiguous.

### Phase 2 - Benchmark Protocol

- [x] Define equivalent timer start and identical stop rules.
- [x] Define elapsed time and active human time recording.
- [x] Define draft verification fields and pass/fail rules.
- [x] Define order balancing for the 10 paired trials.
- [x] Create and verify the local result workbook.
- [x] Freeze the protocol before implementation results are observed.

The frozen method is documented in
[ERPNext Controlled Benchmark Protocol](erpnext-benchmark-protocol.md).

### Phase 3 - Credentials and Environment

- [x] Retain the existing Mistral OCR token and verify it with an isolated real-provider smoke test.
- [x] Top up OpenAI provider credit.
- [x] Retain the existing OpenAI extraction token after verifying that it works with the restored
      credit.
- [x] Keep provider tokens only in the ignored `.env` file.
- [x] Run the full Mistral OCR-to-OpenAI extraction smoke test.
- [x] Install and start ERPNext in an isolated local sandbox.
- [x] Replace the ERPNext default Administrator password.
- [x] Create a dedicated ERPNext integration user with `Accounts User` access and API credentials.
- [x] Store ERPNext credentials only in the ignored `.env`.
- [x] Verify ERPNext health and token authentication without printing credentials.

Environment details and repeatable commands are recorded in
[ERPNext Local Environment](erpnext-environment.md).

### Phase 4 - ERP Master Data

- [x] Create separate manual and application-assisted benchmark companies.
- [x] Create method-specific supplier mappings required by the 10 invoices.
- [x] Configure USD/EUR, a fixed EUR-to-USD benchmark rate, payable accounts, service expense
      accounts, 0%/10%/20% tax behavior, and a non-stock service item.
- [x] Separate manual and assisted records without changing source invoice numbers.
- [x] Enable ERPNext supplier-invoice uniqueness for the duplicate scenario.
- [x] Replace the broad `Accounts User` role with a draft-only integration role that cannot submit,
      cancel, or delete Purchase Invoices.
- [x] Verify all 10 cases have a deterministic ERP outcome: six draft-eligible cases and four
      intentional blockers.

The setup and case matrix are recorded in
[ERPNext Benchmark Master Data](erpnext-master-data.md).

### Phase 5 - Integration Design

- [x] Define the ERPNext Purchase Invoice request and response contracts.
- [x] Define field, supplier, account, tax, and line-item mappings.
- [x] Define idempotency and provider lookup behavior.
- [x] Define retryable failure, unknown outcome, and reconciliation rules.
- [x] Define audit events and user-facing delivery states.
- [x] Review the design before implementation.

The frozen boundary, rejected alternatives, and Phase 6 acceptance criteria are documented in
[ERPNext Draft Integration Design](erpnext-integration-design.md). Its machine-readable companion is
[`examples/erpnext/purchase_invoice_contract.json`](../examples/erpnext/purchase_invoice_contract.json).

### Phase 6 - Implementation

- [x] Add an ERPNext client and Purchase Invoice adapter.
- [x] Enforce approval before delivery.
- [x] Force Draft state and reject unsafe provider responses.
- [x] Persist the ERPNext document ID and URL.
- [x] Preserve duplicate protection, retry safety, reconciliation, and audit history.
- [x] Add `Create ERP Draft`, delivery state, actionable error, and `Open in ERPNext` UI.
- [x] Use `ERP draft created` rather than implying that accounting posting is complete.

Implementation evidence includes fake-provider contract tests, API-level replay and unknown-outcome
tests, strict type checking, and a local ERPNext smoke that creates, verifies, reconciles, and then
deletes one non-benchmark Draft. The fixed `T01`-`T10` pack remains untouched.

### Phase 7 - Technical Verification

- [x] Verify approved, unapproved, duplicate, invalid mapping, timeout, reconciliation, and restart
      cases.
- [x] Verify local and ERPNext values match.
- [x] Verify no test can submit or pay a Purchase Invoice.
- [x] Verify credentials and sensitive payloads do not appear in logs.
- [x] Run focused tests followed by the release quality gate.

The dated evidence matrix, real-sandbox finding, and verification commands are recorded in
[ERPNext Phase 7 Technical Verification](erpnext-phase7-verification.md). One non-benchmark Draft is
retained outside Git for manual inspection and must be removed during the Phase 8 reset.

### Phase 8 - Dry Run

- [x] Practice both workflows with a non-benchmark synthetic fixture.
- [x] Reset the retained Phase 7 Draft before practice.
- [x] Complete and reset an automated end-to-end technical rehearsal through upload, live provider
      extraction, reviewer correction, approval, and verified ERPNext Draft creation.
- [x] Reset the Phase 8 practice Draft before measurement.
- [x] Confirm timer rules and evidence capture are practical.
- [ ] Freeze code, configuration, and procedure before the formal comparison.

The exact operator procedure and commands are recorded in
[ERPNext Phase 8 Dry Run](erpnext-phase8-dry-run.md). Dry-run PDFs, timings, ERP IDs, and the freeze
manifest remain under ignored `_private_data/` storage.

### Phase 9 - Benchmark Execution

- [ ] Run both workflows for all 10 invoices under the frozen protocol.
- [ ] Use the planned crossover order for all 20 trials.
- [ ] Record elapsed time, active human time, corrections, draft correctness, failures, and ERP ID.
- [ ] Retain interrupted or failed formal outcomes according to the protocol.

### Phase 10 - Analysis

- [ ] Calculate median manual and assisted elapsed time.
- [ ] Calculate median manual and assisted active human time.
- [ ] Calculate time reduction, draft accuracy, first-pass success, correction rate, integration
      failure rate, and duplicate-prevention result.
- [ ] Separate provider wait, ERP wait, and human work.
- [ ] Explain outliers and failed cases.

### Phase 11 - Documentation and Release

- [ ] Publish aggregate results, limitations, and selected non-sensitive evidence.
- [ ] Update the README and case study without exposing private documents or secrets.
- [x] Run final regression and packaging checks.
- [ ] Freeze the benchmark after one final results push.

## Commit and Push Strategy

Work on `feature/erpnext-integration`. Commit locally at meaningful milestones:

1. `feat: add ERPNext draft invoice integration`
2. `test: verify ERP approval and duplicate safeguards`
3. `feat: add ERP delivery states and actions`
4. `docs: add controlled ERP benchmark protocol`
5. `docs: publish ERP benchmark results`

Push only at two checkpoints:

1. after the integration and technical quality gate pass;
2. after the benchmark and final documentation are complete.

Do not commit `.env`, API tokens, ERPNext databases, raw private invoices, private labels, or local
benchmark worksheets containing sensitive paths or source content.

## Permitted Final Claim

No workflow-time claim is currently permitted. After a valid formal run, use the scoped reporting
template in the [controlled benchmark protocol](erpnext-benchmark-protocol.md) and link the
machine-readable evidence beside the claim.
