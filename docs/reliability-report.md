# Reliability Report

Status: local portfolio results last verified on 22 July 2026.

## What is measured

I track three results separately:

1. Did the providers extract the expected invoice fields?
2. Did deterministic validation return the expected business result?
3. Did the workflow enforce reviewer, approval, and export rules?

Keeping these results separate makes it easier to tell whether a failure came from extraction,
validation, or the workflow itself.

## Invoice scenario results

- dataset: `examples/benchmark/datasets/invoice_scenarios_v1`
- size: 20 deterministic synthetic PDF invoices
- parser: Mistral OCR (`mistral-ocr-latest`)
- extractor: retired OpenAI-compatible provider; the current evaluation uses the OpenAI API

| Iteration              | Field match | Fully matched documents | Validation behavior | Provider errors |
| ---------------------- | ----------: | ----------------------: | ------------------: | --------------: |
| Initial                |   157 / 160 |                 17 / 20 |             18 / 20 |          0 / 20 |
| Anti-inference prompt  |   159 / 160 |                 19 / 20 |             19 / 20 |          0 / 20 |
| Vendor grounding guard |   160 / 160 |                 20 / 20 |             20 / 20 |          0 / 20 |

The initial run filled three fields that were intentionally missing. Stronger null instructions
corrected the date and tax values. A seller-context guard then rejected an ambiguous platform
header that had been returned as the vendor.

The failed outputs were kept so the improvement can be reproduced instead of being reported only
from the final run.

## Workflow checks

- Real-provider processing stopped at `needs_review`; confidence did not auto-approve an invoice.
- Explicit reviewer approval moved the clean invoice to `approved`.
- The duplicate pair produced one reviewable invoice and one `duplicate_invoice` blocker.
- The duplicate UI disabled approval, and the backend refused the same request independently.
- Correction and rejection remained available.
- Approved, rejected, and exported invoices could not be changed through the intake draft API.
- Export required approval and recorded each delivery attempt.
- Focused tests cover authentication, role, workspace, CSRF, and state-transition rules.

## Run records

The technical APIs keep local records for:

- run traces and tool calls;
- expected and selected tools;
- blocked actions;
- human escalation;
- dataset and planning versions;
- prompt-version and run-window comparisons.

Some run metrics remain placeholders. Token cost is omitted when no real planner cost was recorded.
Run-window comparison remains a local diagnostic.

## Automated verification

The clean-commit release command runs:

- Python dependency audit, Ruff formatting and lint, complexity checks, and the backend test suite;
- frontend dependency review, formatting, lint, unit tests, and production build;
- fixture-based browser checks across product routes;
- one real local browser journey using React, FastAPI, SQLite, and the worker.

The exact counts, environment versions, durations, and dependency exceptions are stored in
`docs/evidence/release-verification.json`.

The frontend check currently includes one time-limited exception for a React Router server-action
advisory. The affected server feature is not used by this client-only Vite application.

## Limitations

- The invoice set is synthetic and intentionally small.
- A perfect final controlled run is not a production accuracy estimate.
- The recorded 1.09-second average provider latency was one local observation, not an SLA.
- False-positive and false-negative rates have not been measured on customer data.
- Reviewer time, cost, and error reduction have not been measured.
- Technical traces show that the controls are implemented. They do not show long-term production
  operations.

Reproduction commands and detailed extraction records are available in
`docs/invoice-scenarios-v1-evidence.md`.
