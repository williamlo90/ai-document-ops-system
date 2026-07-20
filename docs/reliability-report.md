# Reliability Report

Status: verified local portfolio evidence as of 15 July 2026.

## Evidence Layers

The project separates three questions that should not be collapsed into one score:

1. Did providers extract the expected invoice fields?
2. Did deterministic validation produce the expected business result?
3. Did the workflow enforce reviewer, approval, and execution boundaries?

## Invoice Scenario Evidence

- dataset: `examples/benchmark/datasets/invoice_scenarios_v1`
- size: 20 deterministic synthetic PDF invoices
- parser: Mistral OCR (`mistral-ocr-latest`)
- extractor: retired OpenAI-compatible provider; current evaluation uses the OpenAI API instead

| Iteration | Field match | Fully matched documents | Validation behavior | Provider errors |
| --- | ---: | ---: | ---: | ---: |
| Initial | 157 / 160 | 17 / 20 | 18 / 20 | 0 / 20 |
| Anti-inference prompt | 159 / 160 | 19 / 20 | 19 / 20 | 0 / 20 |
| Vendor grounding guard | 160 / 160 | 20 / 20 | 20 / 20 | 0 / 20 |

The initial failures were preserved as evidence. The model incorrectly filled three intentionally
missing fields. Null-handling instructions corrected date and tax. A deterministic seller-context
guard rejected an ambiguous platform header returned as the vendor.

## Workflow Safety Evidence

- real-provider processing stopped at `needs_review`; no high-confidence result auto-approved
- explicit reviewer approval changed the clean invoice to `approved`
- the duplicate pair produced one clean review item and one `duplicate_invoice` blocker
- approval was disabled in the duplicate UI and refused independently by the backend
- correction and rejection remained available
- approved, rejected, and exported invoices were immutable through the intake draft API
- export required an approved state and recorded delivery attempts
- authentication, role, workspace, CSRF, and state-transition boundaries have focused tests

## Run and Agent Evidence

The technical APIs retain local evidence for:

- run traces and tool calls
- expected versus selected tool behavior
- blocked action counts
- human escalation
- scenario dataset and planning versions
- prompt-version and run-window comparisons

Some run metrics are placeholders by design. Token cost is not claimed where no real LLM planner
cost is recorded, and run-window comparison is not described as a persisted production regression
system.

## Automated Verification

- backend: 370 passed, 2 skipped
- frontend: 11 passed
- backend Ruff check: passed
- frontend lint: passed
- frontend production build: passed
- npm production dependency audit: no known vulnerabilities at verification time

## Claim Boundary

- the invoice set is synthetic and intentionally small
- a perfect final controlled run is not a production accuracy estimate
- 1.09 seconds average provider latency was one local observation, not an SLA
- no false-positive or false-negative rate has been measured on customer data
- no business time, cost, or error reduction has been measured
- technical traces demonstrate implemented controls, not production operations maturity

Detailed extraction evidence and reproduction commands are in
`docs/invoice-scenarios-v1-evidence.md`.
