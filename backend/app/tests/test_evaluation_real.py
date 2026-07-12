from __future__ import annotations

import json
import unittest
from pathlib import Path


FIXTURES = Path(__file__).resolve().parents[3] / "examples" / "evaluation" / "real"
EXPECTED = FIXTURES / "expected_real_invoices.json"
PREDICTED = FIXTURES / "predicted_real_invoices.json"
REPORT = FIXTURES / "real_evaluation_report.json"

EVALUATED_FIELDS = {
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
}


class RealFixtureTests(unittest.TestCase):
    def test_expected_fixture_exists(self) -> None:
        self.assertTrue(EXPECTED.exists())

    def test_expected_fixture_includes_all_evaluated_fields(self) -> None:
        records = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertGreater(len(records), 0)
        for record in records:
            self.assertIn("document_id", record)
            for field in EVALUATED_FIELDS:
                self.assertIn(field, record)

    def test_predicted_fixture_exists(self) -> None:
        self.assertTrue(PREDICTED.exists())

    def test_predicted_fixture_is_valid_json_list(self) -> None:
        data = json.loads(PREDICTED.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        if data:
            self.assertIn("document_id", data[0])

    def test_evaluation_report_exists(self) -> None:
        self.assertTrue(REPORT.exists())

    def test_evaluation_report_has_expected_keys(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertIn("documents_total", report)
        self.assertIn("fields_total", report)
        self.assertIn("fields_matched", report)
        self.assertIn("field_accuracy", report)
        self.assertIn("by_field", report)
        self.assertIn("failures", report)

    def test_no_fixture_paths_reference_upload_folder(self) -> None:
        for fixture_path in [EXPECTED, PREDICTED, REPORT]:
            content = fixture_path.read_text(encoding="utf-8")
            self.assertNotIn("backend/data/uploads", content)

    def test_fixture_set_from_app_module_can_be_evaluated(self) -> None:
        from app.evaluation.invoice import evaluate_invoices, report_to_dict

        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        predicted = json.loads(PREDICTED.read_text(encoding="utf-8"))
        report = evaluate_invoices(expected, predicted)
        data = report_to_dict(report)
        self.assertEqual(data["documents_total"], len(expected))
        self.assertEqual(data["fields_total"], len(expected) * len(EVALUATED_FIELDS))


if __name__ == "__main__":
    unittest.main()
