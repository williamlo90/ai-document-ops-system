from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.benchmark.metrics import (
    benchmark_metrics_to_dict,
    calculate_benchmark_metrics,
)
from app.benchmark.models import BenchmarkRun, ProviderRunResult


def _expected_record(document_id: str, total: str = "110.00") -> dict[str, str]:
    return {
        "document_id": document_id,
        "vendor_name": "Acme Logistics",
        "invoice_number": "INV-001",
        "invoice_date": "2026-06-18",
        "due_date": "2026-07-18",
        "subtotal": "100.00",
        "tax": "10.00",
        "total": total,
        "currency": "USD",
    }


def _predicted_fields(total: str | None = "110.00") -> dict[str, str | None]:
    return {
        "vendor_name": "Acme Logistics",
        "invoice_number": "INV-001",
        "invoice_date": "2026-06-18",
        "due_date": "2026-07-18",
        "subtotal": "100.00",
        "tax": "10.00",
        "total": total,
        "currency": "USD",
    }


class BenchmarkMetricsTests(unittest.TestCase):
    def test_all_correct_results_have_full_success(self) -> None:
        run = _run(
            ProviderRunResult("doc-1", "mock", _predicted_fields(), 10.0),
            ProviderRunResult("doc-2", "mock", _predicted_fields("220.00"), 30.0),
        )
        expected = [_expected_record("doc-1"), _expected_record("doc-2", "220.00")]

        metrics = calculate_benchmark_metrics(run, expected)

        self.assertEqual(metrics.evaluation.field_accuracy, 1.0)
        self.assertEqual(metrics.document_success_rate, 1.0)
        self.assertEqual(metrics.documents_succeeded, 2)
        self.assertEqual(metrics.documents_failed, 0)
        self.assertEqual(metrics.provider_error_rate, 0.0)
        self.assertEqual(metrics.missing_field_rate, 0.0)
        self.assertEqual(metrics.latency.total_ms, 40.0)
        self.assertEqual(metrics.latency.average_ms, 20.0)
        self.assertEqual(metrics.latency.min_ms, 10.0)
        self.assertEqual(metrics.latency.max_ms, 30.0)

    def test_field_mismatch_fails_document_without_provider_error(self) -> None:
        run = _run(ProviderRunResult("doc-1", "mock", _predicted_fields("999.00"), 10.0))

        metrics = calculate_benchmark_metrics(run, [_expected_record("doc-1")])

        self.assertEqual(metrics.documents_succeeded, 0)
        self.assertEqual(metrics.documents_failed, 1)
        self.assertEqual(metrics.document_success_rate, 0.0)
        self.assertEqual(metrics.provider_error_rate, 0.0)
        self.assertEqual(metrics.missing_field_rate, 0.0)

    def test_provider_error_counts_as_failed_document_and_missing_fields(self) -> None:
        run = _run(
            ProviderRunResult(
                "doc-1",
                "mock",
                {},
                0.0,
                error="parser_failed",
            )
        )

        metrics = calculate_benchmark_metrics(run, [_expected_record("doc-1")])

        self.assertEqual(metrics.documents_succeeded, 0)
        self.assertEqual(metrics.documents_failed, 1)
        self.assertEqual(metrics.provider_error_rate, 1.0)
        self.assertEqual(metrics.invalid_schema_rate, 1.0)
        self.assertEqual(metrics.missing_field_rate, 1.0)

    def test_partial_missing_field_rate(self) -> None:
        fields = _predicted_fields()
        fields["total"] = None
        run = _run(ProviderRunResult("doc-1", "mock", fields, 10.0))

        metrics = calculate_benchmark_metrics(run, [_expected_record("doc-1")])

        self.assertEqual(metrics.missing_field_rate, 0.125)
        self.assertEqual(metrics.evaluation.fields_matched, 7)

    def test_metrics_to_dict_rounds_and_includes_business_metrics(self) -> None:
        run = _run(ProviderRunResult("doc-1", "mock", _predicted_fields(), 10.0))
        metrics = calculate_benchmark_metrics(run, [_expected_record("doc-1")])

        data = benchmark_metrics_to_dict(metrics)

        self.assertEqual(data["document_success_rate"], 1.0)
        self.assertEqual(data["provider_error_rate"], 0.0)
        self.assertEqual(data["missing_field_rate"], 0.0)
        self.assertIn("latency", data)
        self.assertIn("cost_estimate", data)


def _run(*results: ProviderRunResult) -> BenchmarkRun:
    now = datetime.now(timezone.utc)
    return BenchmarkRun(
        dataset_name="unit",
        provider_name="mock",
        results=tuple(results),
        started_at=now,
        finished_at=now,
    )


if __name__ == "__main__":
    unittest.main()
