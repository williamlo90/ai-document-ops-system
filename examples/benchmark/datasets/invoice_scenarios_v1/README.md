# Invoice Scenarios V1

This is a deterministic synthetic benchmark set for invoice extraction and workflow checks. It contains no customer or personal data.

## Coverage

The 20 PDF-backed cases include:

- ordinary USD, EUR, GBP, SGD, and IDR invoices
- zero tax, multiple line items, long vendor names, and high values
- missing vendor, invoice number, invoice date, due date, and tax
- total mismatch, invalid date order, unsupported currency, and zero total
- a duplicate invoice pair
- low-contrast, rotated, and multi-page layouts

Each record in `expected.json` contains the printed field ground truth plus expected validation codes. All processed invoices must still stop at `needs_review`; none are expected to auto-approve.

## Regenerate

```powershell
python scripts/generate_invoice_scenario_dataset.py
```

The generator uses `reportlab`, which is included in both platform development locks. Output is
deterministic, so regenerating unchanged fixtures should not alter Git content.

Run the configured real providers across the full set with an explicit safety-limit override:

```powershell
$env:BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS = "20"
python scripts/run_real_fixture_extraction.py "$env:TEMP\invoice-scenarios-predicted.json" `
  --dataset examples/benchmark/datasets/invoice_scenarios_v1 `
  --report "$env:TEMP\invoice-scenarios-report.json"
```

## Limits of this dataset

- This is a `small_golden_set`, not a statistically representative production benchmark.
- Synthetic accuracy does not establish accuracy on customer invoices.
- The duplicate pair records business identity for workflow testing; field accuracy alone does not prove duplicate detection.
- High-value documents remain human-reviewed. This dataset does not claim a learned fraud or anomaly model.
