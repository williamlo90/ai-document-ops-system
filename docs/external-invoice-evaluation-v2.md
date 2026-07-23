# External Invoice Evaluation V2

Run date: 20 July 2026

## Verdict

The V2 provider stack passed every predeclared holdout gate, but it did not achieve perfect field
extraction. On a sealed 10-document holdout, all documents completed, field accuracy was 98.75%,
and validation and approval-blocker accuracy were both 100%. One compressed invoice received a
due date that was absent from the golden label. It did not change the expected validation outcome,
but it remains a genuine hallucination.

This is evidence of bounded performance on an external licensed synthetic pack. It is not evidence
of production accuracy, customer value, or robustness across the invoice market.

## Dataset And Split

- Source: [FATURA on Zenodo](https://zenodo.org/records/8261508), CC BY 4.0.
- Class: external licensed synthetic invoices, not customer data.
- Pack: 25 source layouts that do not overlap with the 25 V1 source layouts.
- Split: 15 diagnostic documents and 10 holdout documents.
- The holdout labels and PDFs were sealed with SHA-256 before any V2 provider call.
- Raw PDFs, OCR, labels, per-document predictions, and the experiment ledger remain outside Git.

## Predeclared Holdout Gates

| Gate                        |    Threshold |         Result |
| --------------------------- | -----------: | -------------: |
| Provider success            |         100% |   100% (10/10) |
| Field accuracy              | At least 95% | 98.75% (79/80) |
| Exact-document rate         | At least 80% |     90% (9/10) |
| Validation-code exact match | At least 90% |           100% |
| Approval-blocker accuracy   |         100% |           100% |
| Source-evidence coverage    | At least 95% |           100% |
| Risky false negative        |         Zero |           Zero |

Average end-to-end provider latency was 4.76 seconds per document during this local run. The
estimated list-price cost was $0.063624 for 10 OCR pages, 7,271 input tokens, and 4,038 output
tokens. Hosted latency and billing can change; provider records remain authoritative.

## Bounded Diagnostic Iteration

The first V2 diagnostic run exposed three vendor-grounding failures: one unsafe seller inference
and two valid sellers rejected. Two bounded changes followed:

1. reject address-like, buyer, bill-to, and ship-to identities while preserving seller names in
   invoice-title context;
2. require an exact identity-line match so a URL or email domain cannot invent a vendor name.

The diagnostic progression was 97.50% field accuracy, then 99.17%, then 100%. The final diagnostic
and sealed holdout used the same prompt hash and critical-code hash. The holdout was not used to
make another code change.

## Provider Recovery Context

The V1 sealed holdout originally completed only 1 of 10 documents because the hosted extractor was
unavailable. Re-running those already opened documents with Mistral OCR and OpenAI extraction
completed 10 of 10, but this is only provider-recovery evidence, not a second blind holdout. It also
showed weaker accuracy than V2 and remains in the experiment log.

## Known Limits

- The remaining due-date hallucination shows that missing optional fields are not perfectly
  controlled.
- Duplicate detection was not measured in V2 because the split contained no positive duplicate
  pair; deterministic duplicate behavior is covered separately by scenario and API tests.
- The dataset is synthetic and has no measured business baseline, time saving, or customer outcome.
- The recorded runs used a dirty worktree. Matching critical-code and prompt fingerprints preserve
  the evaluated implementation identity. Ruff formatting after the run changed the source byte
  hash without an intended behavior change. A later OpenAI-only configuration migration also added
  explicit `store=false`; tests were rerun, but a clean-release run cannot retroactively make this
  holdout blind again.
- No result here removes the requirement for a human reviewer before consequential execution.

## Evidence

- [Initial diagnostic aggregate](evidence/external-invoice-v2-diagnostic-initial.json)
- [Final diagnostic aggregate](evidence/external-invoice-v2-diagnostic-final.json)
- [Sealed holdout aggregate](evidence/external-invoice-v2-holdout-final.json)
- [Full experiment log](evaluation-experiment-log.md)
- [Evaluation protocol](evaluation-experiment-protocol.md)
