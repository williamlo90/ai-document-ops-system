from __future__ import annotations

import unittest

from app.evaluation.invoice import evaluate_invoices, report_to_dict


class InvoiceEvaluationTests(unittest.TestCase):
    def test_evaluates_field_exact_match_with_normalization(self) -> None:
        expected = [
            {
                "document_id": "doc-1",
                "vendor_name": "Acme Logistics",
                "invoice_number": "INV-001",
                "invoice_date": "2026-06-18",
                "due_date": "2026-07-18",
                "subtotal": "100.00",
                "tax": "10.00",
                "total": "110.00",
                "currency": "USD",
            }
        ]
        predicted = [
            {
                "document_id": "doc-1",
                "vendor_name": "ACME Logistics",
                "invoice_number": "INV-001",
                "invoice_date": "2026-06-18",
                "due_date": "2026-07-19",
                "subtotal": "100",
                "tax": "10.0",
                "total": "111.00",
                "currency": "usd",
            }
        ]

        report = evaluate_invoices(expected, predicted)

        self.assertEqual(report.documents_total, 1)
        self.assertEqual(report.fields_total, 8)
        self.assertEqual(report.fields_matched, 6)
        self.assertEqual(report.by_field["vendor_name"], 1)
        self.assertEqual(report.by_field["due_date"], 0)
        self.assertEqual(report.by_field["total"], 0)
        self.assertEqual(len(report.failures), 2)

    def test_missing_prediction_counts_every_field_as_failure(self) -> None:
        report = evaluate_invoices(
            [
                {
                    "document_id": "missing",
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "INV-001",
                    "invoice_date": "2026-06-18",
                    "due_date": "2026-07-18",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "110.00",
                    "currency": "USD",
                }
            ],
            [],
        )

        self.assertEqual(report.fields_total, 8)
        self.assertEqual(report.fields_matched, 0)
        self.assertEqual(len(report.failures), 8)

    def test_expected_records_must_include_all_evaluated_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing fields"):
            evaluate_invoices([{"document_id": "partial", "total": "10.00"}], [])

    def test_report_to_dict_rounds_accuracy_and_serializes_failures(self) -> None:
        report = evaluate_invoices(
            [
                {
                    "document_id": "doc-1",
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "INV-001",
                    "invoice_date": "2026-06-18",
                    "due_date": "2026-07-18",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "10.00",
                    "currency": "USD",
                }
            ],
            [
                {
                    "document_id": "doc-1",
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "INV-001",
                    "invoice_date": "2026-06-18",
                    "due_date": "2026-07-18",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "11.00",
                    "currency": "USD",
                }
            ],
        )

        data = report_to_dict(report)

        self.assertEqual(data["field_accuracy"], 0.875)
        self.assertEqual(data["failures"][0]["field_name"], "total")


if __name__ == "__main__":
    unittest.main()
