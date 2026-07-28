# Evaluation Experiment Log

This is the sanitized public index for provider-backed invoice experiments. Detailed predictions,
OCR text, raw PDFs, golden labels, and the append-only `experiment_index.jsonl` remain in the
private dataset directory outside Git.

## Tracking Contract

Every provider run records:

- experiment ID and UTC timestamp;
- dataset, critical-code, and prompt SHA-256 fingerprints;
- Git commit and dirty-worktree state;
- provider, requested model, endpoint host, retry policy, and attempt outcome;
- provider-reported OCR pages and input, cached-input, and output tokens;
- latency, quality metrics, failure taxonomy, and a dated list-price cost estimate.

Runs are appended, not overwritten. Failed and intermediate runs remain visible so a later fix
cannot erase the evidence that motivated it. Raw records are private; selected aggregate JSON
files in `docs/evidence/` contain no document text or credentials.

## Tracked Runs On 20 July 2026

| Experiment         | Purpose                         | Docs |  Field | Exact doc | Validation | Blocker | Estimated USD | Observed failure                                                     |
| ------------------ | ------------------------------- | ---: | -----: | --------: | ---------: | ------: | ------------: | -------------------------------------------------------------------- |
| `20260720T041427Z` | V1 OpenAI diagnostic            |   15 |   100% |      100% |       100% |    100% |     $0.098391 | None                                                                 |
| `20260720T041657Z` | V1 provider-recovery comparison |   10 |    95% |       60% |        90% |     90% |     $0.066425 | Four hallucinated values; one evidence and validation mismatch       |
| `20260720T042050Z` | V2 initial diagnostic           |   15 | 97.50% |       80% |        80% |  86.67% |     $0.097302 | One hallucinated and two missing values; three validation mismatches |
| `20260720T042510Z` | Three-case vendor fix check     |    3 |   100% |      100% |       100% |    100% |     $0.018555 | None                                                                 |
| `20260720T042532Z` | V2 diagnostic after first fix   |   15 | 99.17% |    93.33% |     93.33% |    100% |     $0.097365 | One vendor hallucination from a URL domain                           |
| `20260720T042812Z` | One-case domain-grounding check |    1 |   100% |      100% |       100% |    100% |     $0.006043 | None                                                                 |
| `20260720T042832Z` | V2 final diagnostic             |   15 |   100% |      100% |       100% |    100% |     $0.096794 | None                                                                 |
| `20260720T043136Z` | V2 sealed holdout               |   10 | 98.75% |       90% |       100% |    100% |     $0.063624 | One hallucinated due date; no approval consequence                   |

The tracked runs total an estimated **$0.544499** at the dated list prices. This excludes smoke
checks and provider-backed integration tests. Provider billing dashboards remain authoritative,
especially for failed calls that return no usage metadata.

## OpenAI-Only Migration Smoke

After removing the retired provider configuration, the committed synthetic sample was processed
once through Mistral OCR and the OpenAI API. The run completed one OCR page with 813 input tokens,
383 output tokens, and zero validation errors using `gpt-5.4-mini-2026-03-17`. Its estimated
list-price cost was $0.006333. This is a configuration smoke check, not an accuracy experiment, and
is intentionally excluded from the evaluation total above.

## Current-Provider Release Diagnostics On 28 July 2026

The first clean-commit 20-document attempt failed closed without promoting a partial score. The
runner at that commit preserved the failed attempt count but not the document-stage failure detail,
which exposed an observability gap.

After adding a sanitized failure record, the next clean attempt processed 19 of 20 documents and
made 40 provider calls. `european_number_format` failed at the extractor with
`invalid_extractor_response`; no OCR text, prompt, response, or invoice content was retained. The
failure record predates failure-path cost preservation, so its cost is explicitly unavailable. The
diagnosis led to deterministic normalization for localized decimal output and a regression test.
No partial quality result is reported as a pass.

| Experiment                             | Commit    | Result        | Field | Exact doc | Validation | Evidence | Calls | Estimated USD | Outcome                                 |
| -------------------------------------- | --------- | ------------- | ----: | --------: | ---------: | -------: | ----: | ------------: | --------------------------------------- |
| `1cb6fe9a-e3f3-497a-bf48-8a0da527d87c` | `26c26fa` | 19/20, failed |     - |         - |          - |        - |    40 |   unavailable | Localized decimal rejected by extractor |
| `97ba567f-bd40-446e-8808-11706e50a54a` | `952e557` | 20/20, passed |  100% |      100% |       100% |    87.1% |    40 |     $0.129488 | None                                    |

The passing rerun averaged 3.69 seconds observed latency per document. Its cost uses the dated
pricing snapshot embedded in the record; provider billing remains authoritative.

## Interpretation Rules

- The V1 recovery run is a provider comparison on a previously opened holdout, not a new blind
  holdout.
- Targeted diagnostic reruns are debugging checks and are never reported as holdout evidence.
- The V2 holdout was sealed before provider calls and run once after the diagnostic fixes were
  frozen.
- A 100% diagnostic score is not a production claim. The V2 holdout's due-date hallucination is a
  known remaining limitation.
- The provider-backed runs used a dirty worktree. The manifests therefore record both that fact
  and a critical-code hash; the matching final diagnostic and holdout hash is
  `0c1fa3dbd00ecd67b0db244eb608cca59ba397ec6851b03ce0075e880e1d82a4`.
- Ruff mechanically formatted four tracked source files after the provider calls. The packaged
  source byte hash is therefore
  `3efd76e0c2c0d5cbe13439aa2d6d0dcae0dffe9c9140a1d3f903d1bf3b4d54fb`; targeted tests passed,
  but the public record does not pretend that this later byte state was the sealed-holdout state.
- The subsequent OpenAI-only configuration migration added an explicit `store=false` request and
  changed the current critical-code hash to
  `4d1b2695e93a75e7b60e5122ef17c5c42262efedcf3c4781c436b0d7654d1765`. This hardening is
  regression-tested but is not presented as a fresh sealed-holdout run.

## Public Evidence

- [V1 OpenAI diagnostic aggregate](evidence/external-invoice-openai-v1-diagnostic.json)
- [V1 provider-recovery aggregate](evidence/external-invoice-openai-v1-holdout-recovery.json)
- [V2 initial diagnostic aggregate](evidence/external-invoice-v2-diagnostic-initial.json)
- [V2 final diagnostic aggregate](evidence/external-invoice-v2-diagnostic-final.json)
- [V2 sealed holdout aggregate](evidence/external-invoice-v2-holdout-final.json)
- [Current-provider failed diagnostic](evidence/current-provider-diagnostic.failed-20260728T080824Z.json)
- [Current-provider passing diagnostic](evidence/current-provider-diagnostic.json)
- [Experiment protocol](evaluation-experiment-protocol.md)
