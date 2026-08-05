# Invoice Scenarios V1 Evidence

Run date: 15 July 2026

## Scope

- Dataset: `examples/benchmark/datasets/invoice_scenarios_v1`
- Size: 20 deterministic synthetic PDF invoices
- Parser: Mistral OCR (`mistral-ocr-latest`)
- Extractor: retired OpenAI-compatible provider; not part of the current runtime configuration
- Environment: local Windows development run
- Sensitive data: none

The set includes ordinary invoices, missing fields, deterministic validation failures, a business duplicate pair, low-contrast text, rotated content, and a two-page invoice.

## Observed Iterations

| Run                    |        Field match | Fully matched documents | Validation behavior | Provider errors | Average latency |
| ---------------------- | -----------------: | ----------------------: | ------------------: | --------------: | --------------: |
| Initial                | 157 / 160 (98.12%) |           17 / 20 (85%) |             18 / 20 |          0 / 20 |          1.99 s |
| Anti-inference prompt  | 159 / 160 (99.38%) |           19 / 20 (95%) |             19 / 20 |          0 / 20 |          1.13 s |
| Vendor grounding guard |   160 / 160 (100%) |          20 / 20 (100%) |             20 / 20 |          0 / 20 |          1.09 s |

The initial run incorrectly filled three intentionally missing fields: vendor, invoice date, and tax. Stronger null-handling instructions corrected date and tax. A deterministic seller-context guard then rejected a platform header that the model had mistaken for the missing vendor.

The guard is intentionally conservative. A vendor name must appear with a seller label or nearby business identity/address evidence. Ambiguous headers become `null`, which forces human correction instead of silently treating a guessed company as the vendor.

## Workflow Verification

The duplicate pair was also processed through the local application with the real providers:

- `duplicate_original.pdf` stopped at `needs_review` with no validation error.
- `duplicate_copy.pdf` stopped at `needs_review` with `duplicate_invoice`.
- The reviewer queue separated the pair into one `Waiting decision` item and one `Needs correction` item.
- The duplicate review screen showed the source PDF and validation reason, disabled approval, and kept correction and rejection available.
- The backend independently rejects approval while any error-level validation issue remains unresolved.

## Reproduce

Configure credentials in the ignored local `.env`, then run:

```powershell
$env:BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS = "20"
python scripts/run_real_fixture_extraction.py "$env:TEMP\invoice-scenarios-predicted.json" `
  --dataset examples/benchmark/datasets/invoice_scenarios_v1 `
  --report "$env:TEMP\invoice-scenarios-report.json"
```

Run the deterministic regression suite without credentials:

```powershell
$env:ENV_FILE = ".env.example"
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend/app/tests -t backend
```

## Limits of this evidence

- This is a synthetic `small_golden_set`, not customer validation or a statistically representative benchmark.
- A perfect final run on these 20 controlled fixtures is not a production accuracy claim.
- Latency is one local observation and varies with network and provider conditions.
- Duplicate workflow behavior is one deterministic local observation, not a measured false-positive or false-negative rate.
- Approval gating and export blocking are covered by workflow tests and provider-backed smoke flows, not by field accuracy alone.
