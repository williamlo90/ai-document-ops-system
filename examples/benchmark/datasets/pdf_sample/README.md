# PDF Sample Benchmark Dataset

This dataset contains one public synthetic invoice PDF and matching ground truth.

It exists to verify that provider benchmarks can run from a real PDF-backed fixture, not only from JSON-only expected records.

## Files

- `expected.json` - ground truth invoice fields.
- `documents/sample_invoice.pdf` - source PDF used by parser providers.

## Notes

- This is a bootstrap fixture, not a statistically meaningful benchmark.
- Mock providers can run against it without calling external APIs.
- Real providers can use the `source_file` path when credentials are configured locally.

