from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.benchmark.models import BenchmarkRun, ProviderRunResult
from app.benchmark.report import (
    generate_comparison_json_report,
    generate_comparison_json_report_from_provider_summaries,
    generate_comparison_markdown_report,
    generate_json_report,
    generate_markdown_report,
)


class BenchmarkReportTests(unittest.TestCase):
    def test_json_report_includes_benchmark_metrics(self) -> None:
        run = _run(ProviderRunResult("doc-1", "mock", _fields(), 25.0))

        report = generate_json_report(run, [_expected_record("doc-1")])

        self.assertEqual(report["dataset"], "unit")
        self.assertEqual(report["metrics"]["document_success_rate"], 1.0)
        self.assertEqual(report["metrics"]["provider_error_rate"], 0.0)
        self.assertEqual(report["metrics"]["latency"]["total_ms"], 25.0)
        self.assertIn("cost_estimate", report)

    def test_markdown_report_includes_decision_metrics(self) -> None:
        run = _run(ProviderRunResult("doc-1", "mock", _fields(total="999.00"), 25.0))

        report = generate_markdown_report(run, [_expected_record("doc-1")])

        self.assertIn("Document success rate", report)
        self.assertIn("Missing field rate", report)
        self.assertIn("Provider error rate", report)
        self.assertIn("Field Failures", report)

    def test_comparison_json_ranks_best_provider_first(self) -> None:
        good = _run(
            ProviderRunResult("doc-1", "accurate", _fields(), 50.0),
            provider_name="accurate",
        )
        bad = _run(
            ProviderRunResult("doc-1", "cheap_bad", _fields(total="999.00"), 10.0),
            provider_name="cheap_bad",
        )

        report = generate_comparison_json_report([bad, good], [_expected_record("doc-1")])

        self.assertEqual(report["providers_count"], 2)
        self.assertEqual(report["ranking"][0]["provider"], "accurate")
        self.assertEqual(report["ranking"][0]["rank"], 1)
        self.assertEqual(report["providers"][0]["provider_mode"], "real")
        self.assertIn("limitations", report)

    def test_comparison_json_includes_failure_examples(self) -> None:
        run = _run(
            ProviderRunResult("doc-1", "mock", _fields(total="999.00"), 25.0),
        )

        report = generate_comparison_json_report([run], [_expected_record("doc-1")])

        examples = report["providers"][0]["failure_examples"]
        self.assertEqual(examples[0]["field_name"], "total")
        self.assertEqual(examples[0]["expected"], "110.00")
        self.assertEqual(examples[0]["predicted"], "999.00")

    def test_comparison_json_includes_provider_errors(self) -> None:
        run = _run(
            ProviderRunResult(
                "doc-1",
                "llm_json",
                {},
                25.0,
                error="invalid_extractor_response",
                trace_id="trace-1",
            ),
            provider_name="mistral_ocr+llm_json",
        )

        report = generate_comparison_json_report([run], [_expected_record("doc-1")])

        errors = report["providers"][0]["provider_errors"]
        self.assertEqual(errors[0]["document_id"], "doc-1")
        self.assertEqual(errors[0]["error"], "invalid_extractor_response")
        self.assertEqual(errors[0]["trace_id"], "trace-1")

    def test_comparison_json_can_be_generated_from_saved_provider_summaries(self) -> None:
        mock = generate_comparison_json_report(
            [_run(ProviderRunResult("doc-1", "mock", _fields(total="999.00"), 25.0))],
            [_expected_record("doc-1")],
        )["providers"][0]
        real = generate_comparison_json_report(
            [
                _run(
                    ProviderRunResult("doc-1", "mistral_ocr+llm_json", _fields(), 80.0),
                    provider_name="mistral_ocr+llm_json",
                )
            ],
            [_expected_record("doc-1")],
        )["providers"][0]

        report = generate_comparison_json_report_from_provider_summaries("unit", [mock, real])

        self.assertEqual(report["providers_count"], 2)
        self.assertEqual(report["ranking"][0]["provider"], "mistral_ocr+llm_json")
        self.assertEqual(report["decision"]["recommended_provider"], "mistral_ocr+llm_json")

    def test_comparison_json_includes_decision_summary(self) -> None:
        accurate = _run(
            ProviderRunResult("doc-1", "accurate", _fields(), 80.0),
            provider_name="accurate",
        )
        cheap_fast_bad = _run(
            ProviderRunResult("doc-1", "cheap_fast_bad", _fields(total="999.00"), 5.0),
            provider_name="cheap_fast_bad",
        )

        report = generate_comparison_json_report(
            [cheap_fast_bad, accurate],
            [_expected_record("doc-1")],
        )

        self.assertEqual(report["decision"]["recommended_provider"], "accurate")
        self.assertGreater(report["decision"]["decision_score"], 0)
        self.assertEqual(report["decision"]["scoring_weights"]["document_success_rate"], 0.40)
        self.assertIn("Field accuracy", " ".join(report["decision"]["reasons"]))

    def test_comparison_markdown_includes_ranking_and_limitations(self) -> None:
        run = _run(ProviderRunResult("doc-1", "mock", _fields(), 25.0))

        report = generate_comparison_markdown_report([run], [_expected_record("doc-1")])

        self.assertIn("Provider Benchmark Comparison", report)
        self.assertIn("Provider Ranking", report)
        self.assertIn("Decision Summary", report)
        self.assertIn("Recommended provider", report)
        self.assertIn("Known Limitations", report)
        self.assertIn("Mock provider results", report)


def _run(*results: ProviderRunResult, provider_name: str = "mock") -> BenchmarkRun:
    now = datetime.now(timezone.utc)
    return BenchmarkRun(
        dataset_name="unit",
        provider_name=provider_name,
        results=tuple(results),
        started_at=now,
        finished_at=now,
    )


def _expected_record(document_id: str) -> dict[str, str]:
    return {
        "document_id": document_id,
        **_fields(),
    }


def _fields(total: str = "110.00") -> dict[str, str]:
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


if __name__ == "__main__":
    unittest.main()
