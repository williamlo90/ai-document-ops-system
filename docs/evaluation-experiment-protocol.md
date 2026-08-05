# Evaluation Experiment Protocol

This protocol governs provider-backed invoice evaluation. It exists to keep model, provider,
cost, and failure claims reproducible instead of relying on manually selected runs.

## Evidence Boundary

- PDFs, OCR text, labels, provider responses, and per-document observations remain outside Git.
- Each private run writes an immutable detailed result and appends one record to
  `evaluation_runs/experiment_index.jsonl`.
- Git may contain sanitized aggregate metrics, dataset fingerprints, pricing snapshots, and
  limitations. It must not contain credentials or private document content.
- Failed and superseded runs are preserved. A later successful run does not replace them.

## Run Provenance

Every run records:

- experiment ID and UTC timestamps;
- dataset fingerprint and holdout-seal verification;
- parser and extractor model IDs;
- extraction prompt version and SHA-256 fingerprint;
- Git commit, dirty-worktree state, and critical-code fingerprint;
- retry and rate-limit policy;
- per-stage attempt status and sanitized failure code;
- provider-reported OCR page, document-size, and token usage;
- list-price estimate with an effective date and source URLs;
- accuracy, validation, approval-blocker, evidence, and latency metrics.

Provider billing dashboards remain the source of truth. Repository cost values are estimates from
provider-reported usage and a dated public pricing snapshot. Missing usage on failed requests is
reported as a limitation rather than guessed.

## Diagnostic Gate

The 15-document diagnostic run must satisfy all of the following before holdout evaluation:

- provider success: 15 of 15;
- field accuracy: at least 95 percent;
- approval-blocker accuracy: 100 percent;
- no schema failures;
- no risky invoice incorrectly treated as approval-safe.

Diagnostic failures may justify targeted changes and regression tests. Successful diagnostic
observations may be reused when retrying provider failures, but reuse must be recorded.

## Holdout Policy

- Extraction logic, model snapshots, prompts, and validation rules are frozen before the run.
- A sealed holdout cannot reuse cached observations.
- Retry policy is declared before execution and applies uniformly.
- A completed holdout is not rerun to improve its score.
- Any extraction-logic change after a holdout requires a new, previously unused sealed holdout.

The predeclared V2 acceptance gate is:

- provider success: 10 of 10;
- field accuracy: at least 95 percent;
- exact-document rate: at least 80 percent;
- validation-code exact match: at least 90 percent;
- approval-blocker accuracy: 100 percent;
- source-evidence coverage: at least 95 percent;
- no risky false negative, schema failure, or missing-field hallucination that removes a required
  approval blocker.

The existing V1 holdout has already been evaluated with the previous provider. A rerun is a
provider-recovery comparison, not a new blind holdout. Final robustness claims require a fresh V2
sealed holdout.
