# External Invoice Evaluation V1

Run date: 15 July 2026

## Verdict

This run does **not** establish external invoice robustness.

The extraction path was correct on the documents that reached both providers, but the sealed
holdout exposed a severe hosted-extractor availability limit: 9 of 10 holdout documents ended in
`extractor_http_error` after bounded retries. The honest end-to-end holdout field accuracy is
therefore 10%, not the conditional 100% observed on the single successful document.

## Dataset And Privacy Boundary

- Source: [FATURA on Zenodo](https://zenodo.org/records/8261508), CC BY 4.0.
- Source class: external licensed synthetic invoices, not customer or production data.
- Pack size: 25 invoices selected deterministically from 25 distinct source layouts.
- Split: 15 diagnostic documents and 10 sealed holdout documents.
- Scan profiles: clean, low contrast, soft blur, slight skew, and compressed.
- Raw images, generated PDFs, golden labels, OCR text, and provider responses stay outside Git.
- The holdout label file and all holdout PDFs were sealed with SHA-256 before evaluation.

Only aggregate reports are committed:

- [diagnostic aggregate](evidence/external-invoice-diagnostic-v1.json)
- [sealed holdout aggregate](evidence/external-invoice-holdout-v1.json)

## Observed Results

| Metric | Diagnostic (15) | Sealed holdout (10) |
| --- | ---: | ---: |
| Provider success rate | 93.33% (14/15) | 10.00% (1/10) |
| End-to-end field accuracy | 93.33% | 10.00% |
| End-to-end exact-document rate | 93.33% | 10.00% |
| End-to-end validation-code exact match | 93.33% | 40.00% |
| End-to-end approval-blocker accuracy | 93.33% | 40.00% |
| Field accuracy when both providers succeeded | 100% (14 documents) | 100% (1 document) |
| Source-evidence coverage on correct non-null fields | 87.50% | 85.71% |
| Provider errors | 1 | 9 |

The holdout validation and blocker percentages are not evidence of usable workflow quality because
nine documents never produced an extraction. Some expected no-error outcomes can coincide with an
empty predicted code set, so provider success and end-to-end field accuracy are the controlling
metrics for this run.

## Diagnostic Improvements

The diagnostic split exposed and justified five bounded changes before the holdout:

1. Treat seller names followed by an explicit address, or positioned between an invoice title and
   bill-to block, as grounded business identity evidence.
2. Copy explicitly labeled subtotal, tax, and total values from OCR instead of accepting an LLM
   recalculation when the printed values are inconsistent.
3. Remove inferred tax when no aggregate TAX, VAT, or GST amount is present.
4. Require source page and an exact OCR excerpt; fabricated excerpts no longer count as evidence.
5. Normalize provider strings such as `"null"` to actual missing values at the schema boundary.

The diagnostic runner can reuse successful observations while retrying provider failures. That mode
is forbidden for holdout runs.

## Failure Interpretation

The holdout result separates two questions:

- **Extraction correctness:** one successful holdout document is too small to support a robustness
  claim, even though all evaluated fields and validation behavior matched.
- **Batch availability:** 9 of 10 documents failed at the hosted extractor boundary despite a
  10-second document interval and 30/60-second retry backoff. This is a release blocker for
  evaluation-scale use of the current free endpoint.

The holdout was not rerun to search for a better number. A future infrastructure run must preserve
this first result, use a stable quota or paid endpoint, and report the new run alongside it.

## Reproduce Privately

The source archive and output path must be outside the repository:

```powershell
python scripts/prepare_private_external_invoice_pack.py <FATURA.zip> <private-pack-root>

python scripts/run_private_external_evaluation.py <private-pack-root> `
  <private-diagnostic-aggregate.json> --split diagnostic

python scripts/run_private_external_evaluation.py <private-pack-root> `
  <private-holdout-aggregate.json> --split holdout `
  --rate-limit-seconds 10 --retry-backoff-seconds 30
```

Detailed results remain private. Use `scripts/summarize_private_external_evaluation.py` to regenerate
sanitized aggregate metrics after evaluator-only changes without calling providers again.

## Claim Boundary

- Do not present the diagnostic conditional result as holdout accuracy.
- Do not present one successful holdout document as evidence of general extraction accuracy.
- Do not describe FATURA as real customer data.
- Do not claim production readiness until provider availability and a new predeclared run are
  measured successfully.

## Follow-Up

The failed V1 result remains part of the evidence record. A non-overlapping V2 pack was later run
with a paid OpenAI extractor and is reported separately in
[External Invoice Evaluation V2](external-invoice-evaluation-v2.md). The V1 documents were also
used for a clearly labeled provider-recovery comparison; that comparison is not treated as a new
blind holdout.
