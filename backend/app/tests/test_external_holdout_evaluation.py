from __future__ import annotations

import unittest

from app.evaluation.external_holdout import build_external_evaluation_summary


def _record(document_id: str = "doc-1") -> dict[str, object]:
    return {
        "document_id": document_id,
        "vendor_name": "Acme Logistics",
        "invoice_number": "INV-001",
        "invoice_date": "2026-06-18",
        "due_date": "2026-07-18",
        "subtotal": "100.00",
        "tax": "10.00",
        "total": "110.00",
        "currency": "USD",
        "expected_validation_codes": [],
    }


class ExternalHoldoutEvaluationTests(unittest.TestCase):
    def test_builds_aggregate_metrics_without_document_values(self) -> None:
        expected = [_record()]
        observation = {
            "document_id": "doc-1",
            "predicted_fields": {
                key: value
                for key, value in expected[0].items()
                if key not in {"document_id", "expected_validation_codes"}
            },
            "predicted_validation_codes": [],
            "confidence_fields": ["vendor_name", "total"],
            "evidence_fields": ["vendor_name"],
            "latency_ms": 125.0,
            "error": None,
        }

        summary = build_external_evaluation_summary(
            expected,
            [observation],
            split="diagnostic",
            provider="parser+extractor",
        )

        self.assertEqual(summary["metrics"]["field_accuracy"], 1.0)
        self.assertEqual(summary["metrics"]["provider_success_rate"], 1.0)
        self.assertEqual(summary["metrics"]["document_exact_match_rate"], 1.0)
        self.assertEqual(summary["metrics"]["validation_code_exact_match_rate"], 1.0)
        self.assertEqual(summary["metrics"]["approval_blocker_accuracy"], 1.0)
        self.assertEqual(summary["metrics"]["confidence_metadata_coverage"], 0.25)
        self.assertEqual(summary["metrics"]["source_evidence_coverage"], 0.125)
        self.assertNotIn("doc-1", str(summary))
        self.assertNotIn("Acme Logistics", str(summary))

    def test_provider_error_counts_all_fields_as_end_to_end_failures(self) -> None:
        expected = [_record()]
        expected[0]["due_date"] = None
        observation = {
            "document_id": "doc-1",
            "predicted_fields": {},
            "predicted_validation_codes": [],
            "confidence_fields": [],
            "evidence_fields": [],
            "latency_ms": 5000,
            "error": "extractor_http_error",
        }

        summary = build_external_evaluation_summary(
            expected,
            [observation],
            split="holdout",
            provider="parser+extractor",
        )

        self.assertEqual(summary["metrics"]["provider_success_rate"], 0.0)
        self.assertEqual(summary["metrics"]["field_accuracy"], 0.0)
        self.assertEqual(summary["metrics"]["document_exact_match_rate"], 0.0)
        conditional = summary["metrics"]["conditional_on_provider_success"]
        self.assertEqual(conditional["documents_count"], 0)
        self.assertEqual(conditional["field_accuracy"], 0.0)

    def test_reports_hallucination_validation_mismatch_and_unmeasured_duplicates(self) -> None:
        expected = [_record()]
        expected[0]["due_date"] = None
        expected[0]["expected_validation_codes"] = ["total_mismatch"]
        predicted = {
            key: value
            for key, value in expected[0].items()
            if key not in {"document_id", "expected_validation_codes"}
        }
        predicted["due_date"] = "2026-07-18"
        observation = {
            "document_id": "doc-1",
            "predicted_fields": predicted,
            "predicted_validation_codes": [],
            "confidence_fields": [],
            "evidence_fields": [],
            "latency_ms": 50,
            "error": None,
        }

        summary = build_external_evaluation_summary(
            expected,
            [observation],
            split="holdout",
            provider="parser+extractor",
        )

        self.assertEqual(summary["failure_taxonomy"]["hallucinated_value"], 1)
        self.assertEqual(summary["failure_taxonomy"]["validation_code_mismatch"], 1)
        self.assertEqual(
            summary["metrics"]["duplicate_detection"]["status"],
            "not_measured_no_positive_pairs",
        )

    def test_measures_duplicate_pair_precision_and_recall(self) -> None:
        first = _record("doc-1")
        second = _record("doc-2")
        first["duplicate_group"] = "pair-1"
        second["duplicate_group"] = "pair-1"
        observations = []
        for expected in (first, second):
            observations.append(
                {
                    "document_id": expected["document_id"],
                    "predicted_fields": {
                        key: value
                        for key, value in expected.items()
                        if key
                        not in {"document_id", "expected_validation_codes", "duplicate_group"}
                    },
                    "predicted_validation_codes": [],
                    "confidence_fields": [],
                    "evidence_fields": [],
                    "latency_ms": 50,
                    "error": None,
                }
            )

        summary = build_external_evaluation_summary(
            [first, second],
            observations,
            split="diagnostic",
            provider="parser+extractor",
        )

        duplicate = summary["metrics"]["duplicate_detection"]
        self.assertEqual(duplicate["status"], "measured")
        self.assertEqual(duplicate["precision"], 1.0)
        self.assertEqual(duplicate["recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
