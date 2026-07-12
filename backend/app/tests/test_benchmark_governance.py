from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.benchmark.governance import generate_governance_report
from app.benchmark.models import BenchmarkRun, ProviderRunResult
from app.benchmark.report import generate_json_report


class BenchmarkGovernanceTests(unittest.TestCase):
    def test_governance_report_labels_bootstrap_dataset_without_baseline(self) -> None:
        current = _report(_fields(), provider_name="mock")

        report = generate_governance_report(current)

        self.assertEqual(report["dataset"]["evidence_level"], "bootstrap")
        self.assertTrue(report["dataset"]["is_golden_candidate"])
        self.assertEqual(report["regression"]["status"], "no_baseline")
        self.assertFalse(report["regression"]["has_regression"])
        self.assertIn("bootstrap-level", " ".join(report["limitations"]))

    def test_governance_report_detects_accuracy_regression(self) -> None:
        baseline = _report(_fields(), provider_name="accurate")
        current = _report(_fields(total="999.00"), provider_name="changed_provider")

        report = generate_governance_report(current, baseline)

        self.assertEqual(report["regression"]["status"], "regression_detected")
        self.assertTrue(report["regression"]["has_regression"])
        regressed_metrics = {
            check["metric"] for check in report["regression"]["checks"] if check["regressed"]
        }
        self.assertIn("field_accuracy", regressed_metrics)
        self.assertIn("document_success_rate", regressed_metrics)

    def test_governance_report_passes_when_within_thresholds(self) -> None:
        baseline = _report(_fields(), latency_ms=100.0, provider_name="accurate")
        current = _report(_fields(), latency_ms=110.0, provider_name="accurate_v2")

        report = generate_governance_report(current, baseline)

        self.assertEqual(report["regression"]["status"], "pass")
        self.assertFalse(report["regression"]["has_regression"])
        self.assertEqual(report["decision_evidence"]["field_accuracy"], 1.0)


def _report(
    fields: dict[str, str],
    latency_ms: float = 25.0,
    provider_name: str = "mock",
) -> dict:
    now = datetime.now(timezone.utc)
    run = BenchmarkRun(
        dataset_name="unit",
        provider_name=provider_name,
        results=(
            ProviderRunResult(
                "doc-1",
                provider_name,
                fields,
                latency_ms,
            ),
        ),
        started_at=now,
        finished_at=now,
    )
    return generate_json_report(run, [_expected_record("doc-1")])


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
