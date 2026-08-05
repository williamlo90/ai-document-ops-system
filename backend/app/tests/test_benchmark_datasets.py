from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.benchmark.datasets import (
    DatasetValidationError,
    load_evaluation_dataset,
    records_from_dataset,
)
from app.extraction.schemas import InvoiceData
from app.validation.invoice import validate_invoice


def _valid_record(document_id: str = "invoice-001") -> dict[str, str]:
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
    }


class BenchmarkDatasetTests(unittest.TestCase):
    def test_public_pdf_sample_dataset_loads_source_file(self) -> None:
        dataset_root = (
            Path(__file__).resolve().parents[3]
            / "examples"
            / "benchmark"
            / "datasets"
            / "pdf_sample"
        )

        dataset = load_evaluation_dataset(dataset_root)

        self.assertEqual(dataset.name, "pdf_sample")
        self.assertEqual(len(dataset.documents), 1)
        self.assertEqual(dataset.documents[0].document_id, "sample_invoice")
        self.assertEqual(dataset.documents[0].expected_fields["total"], "93.50")
        self.assertIsNotNone(dataset.documents[0].source_path)
        self.assertTrue(dataset.documents[0].source_path.is_file())

    def test_loads_valid_expected_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "simple_invoice"
            root.mkdir()
            (root / "expected.json").write_text(
                json.dumps([_valid_record()]),
                encoding="utf-8",
            )

            dataset = load_evaluation_dataset(root)

            self.assertEqual(dataset.name, "simple_invoice")
            self.assertEqual(len(dataset.documents), 1)
            self.assertEqual(dataset.documents[0].document_id, "invoice-001")
            self.assertEqual(dataset.documents[0].expected_fields["total"], "110.00")
            self.assertEqual(dataset.root_path, root.resolve())

    def test_missing_expected_json_is_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"
            root.mkdir()

            with self.assertRaises(FileNotFoundError):
                load_evaluation_dataset(root)

    def test_expected_json_must_be_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "expected.json").write_text(
                json.dumps({"document_id": "invoice-001"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DatasetValidationError, "list of records"):
                load_evaluation_dataset(root)

    def test_rejects_missing_required_expected_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _valid_record()
            del record["total"]
            (root / "expected.json").write_text(json.dumps([record]), encoding="utf-8")

            with self.assertRaisesRegex(DatasetValidationError, "missing fields: total"):
                load_evaluation_dataset(root)

    def test_accepts_explicit_null_as_missing_field_ground_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _valid_record()
            record["vendor_name"] = None
            (root / "expected.json").write_text(json.dumps([record]), encoding="utf-8")

            dataset = load_evaluation_dataset(root)

        self.assertIsNone(dataset.documents[0].expected_fields["vendor_name"])

    def test_synthetic_scenario_dataset_has_twenty_pdf_backed_cases(self) -> None:
        dataset_root = (
            Path(__file__).resolve().parents[3]
            / "examples"
            / "benchmark"
            / "datasets"
            / "invoice_scenarios_v1"
        )

        dataset = load_evaluation_dataset(dataset_root)

        self.assertEqual(len(dataset.documents), 20)
        self.assertTrue(all(document.source_path for document in dataset.documents))
        self.assertTrue(all(document.source_path.is_file() for document in dataset.documents))
        missing_vendor = next(
            document for document in dataset.documents if document.document_id == "missing_vendor"
        )
        self.assertIsNone(missing_vendor.expected_fields["vendor_name"])

    def test_synthetic_scenario_ground_truth_matches_expected_validation(self) -> None:
        dataset_root = (
            Path(__file__).resolve().parents[3]
            / "examples"
            / "benchmark"
            / "datasets"
            / "invoice_scenarios_v1"
        )
        dataset = load_evaluation_dataset(dataset_root)

        for document in dataset.documents:
            fields = document.expected_fields
            invoice = InvoiceData(
                vendor_name=fields["vendor_name"],
                invoice_number=fields["invoice_number"],
                invoice_date=_date(fields["invoice_date"]),
                due_date=_date(fields["due_date"]),
                subtotal=_decimal(fields["subtotal"]),
                tax=_decimal(fields["tax"]),
                total=_decimal(fields["total"]),
                currency=fields["currency"],
            )

            actual_codes = {issue.code for issue in validate_invoice(invoice).issues}

            self.assertEqual(
                actual_codes,
                set(fields["expected_validation_codes"]),
                document.document_id,
            )

        duplicate_documents = [
            document
            for document in dataset.documents
            if document.expected_fields.get("duplicate_group") == "summit-dup-01"
        ]
        self.assertEqual(len(duplicate_documents), 2)
        self.assertEqual(
            {document.expected_fields["invoice_number"] for document in duplicate_documents},
            {"SIP-7788"},
        )

    def test_rejects_duplicate_document_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = [_valid_record("invoice-001"), _valid_record("invoice-001")]
            (root / "expected.json").write_text(json.dumps(records), encoding="utf-8")

            with self.assertRaisesRegex(DatasetValidationError, "Duplicate document_id"):
                load_evaluation_dataset(root)

    def test_source_file_must_stay_inside_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dataset"
            root.mkdir()
            outside = Path(tmp) / "outside.pdf"
            outside.write_bytes(b"%PDF-1.4\n")
            record = _valid_record()
            record["source_file"] = "../outside.pdf"
            (root / "expected.json").write_text(json.dumps([record]), encoding="utf-8")

            with self.assertRaisesRegex(DatasetValidationError, "stay inside the dataset"):
                load_evaluation_dataset(root)

    def test_source_file_must_exist_when_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _valid_record()
            record["source_file"] = "documents/invoice-001.pdf"
            (root / "expected.json").write_text(json.dumps([record]), encoding="utf-8")

            with self.assertRaisesRegex(DatasetValidationError, "does not exist"):
                load_evaluation_dataset(root)

    def test_rejects_dataset_root_inside_private_data_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "backend" / "data" / "uploads" / "dataset"
            root.mkdir(parents=True)
            (root / "expected.json").write_text(
                json.dumps([_valid_record()]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DatasetValidationError, "private data/upload"):
                load_evaluation_dataset(root)

    def test_records_from_dataset_round_trips_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "expected.json").write_text(
                json.dumps([_valid_record()]),
                encoding="utf-8",
            )
            dataset = load_evaluation_dataset(root)

            records = records_from_dataset(dataset)

            self.assertEqual(records[0]["document_id"], "invoice-001")
            self.assertEqual(records[0]["vendor_name"], "Acme Logistics")
            self.assertEqual(records[0]["total"], "110.00")


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


if __name__ == "__main__":
    unittest.main()
