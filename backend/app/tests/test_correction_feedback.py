from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.documents.sqlite_repositories import SqliteStore
from app.extraction.schemas import InvoiceData
from app.review.corrections import CorrectionFeedbackService
from app.review.datasets import (
    assert_private_dataset_path,
    private_dataset_jsonl,
    sanitized_correction_summary,
)
from app.review.models import CorrectionReasonSource, CorrectionSource
from app.review.repositories import InMemoryCorrectionEventRepository
from app.review.sqlite_repositories import SqliteCorrectionEventRepository


class CorrectionFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document_id = uuid4()
        self.repository = InMemoryCorrectionEventRepository()
        self.service = CorrectionFeedbackService(self.repository)
        self.ai_output = InvoiceData(
            vendor_name="Acme Logistic",
            invoice_number="INV-001",
            invoice_date=date(2026, 7, 15),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("100.00"),
            currency="USD",
        )

    def test_sequential_corrections_keep_original_ai_and_before_after_values(self) -> None:
        first_output = InvoiceData(
            **{
                **self.ai_output.__dict__,
                "vendor_name": "Acme Logistics",
                "total": Decimal("110.00"),
            }
        )
        first = self.service.capture(
            workspace_id="default",
            document_id=self.document_id,
            before=self.ai_output,
            after=first_output,
            actor="William Lo",
            reason="Matched the vendor and total to the PDF.",
            source=CorrectionSource.INTAKE_CHECK,
        )
        second_output = InvoiceData(**{**first_output.__dict__, "currency": "IDR"})
        second = self.service.capture(
            workspace_id="default",
            document_id=self.document_id,
            before=first_output,
            after=second_output,
            actor="William Lo",
            reason=None,
            requested_reason="Use the currency printed beside the total.",
            source=CorrectionSource.INTAKE_CHECK,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertEqual(first.original_ai_data, self.ai_output)
        self.assertEqual(second.original_ai_data, self.ai_output)
        currency = next(change for change in second.changes if change.field_path == "currency")
        self.assertEqual(currency.original_ai_value, "USD")
        self.assertEqual(currency.before_value, "USD")
        self.assertEqual(currency.after_value, "IDR")
        self.assertEqual(second.reason_source, CorrectionReasonSource.REVIEWER_REQUEST)
        summary = self.service.summary("default", self.document_id)
        assert summary is not None
        self.assertEqual(
            summary["latest_changes"],
            [
                {
                    "field_path": "currency",
                    "original_ai_value": "USD",
                    "before_value": "USD",
                    "after_value": "IDR",
                }
            ],
        )

    def test_no_op_save_does_not_create_feedback_noise(self) -> None:
        event = self.service.capture(
            workspace_id="default",
            document_id=self.document_id,
            before=self.ai_output,
            after=self.ai_output,
            actor="William Lo",
            reason="No changes",
            source=CorrectionSource.INTAKE_CHECK,
        )

        self.assertIsNone(event)
        self.assertEqual(self.repository.records, [])

    def test_private_dataset_has_values_but_public_summary_is_aggregate_only(self) -> None:
        corrected = InvoiceData(**{**self.ai_output.__dict__, "vendor_name": "Acme Logistics"})
        self.service.capture(
            workspace_id="default",
            document_id=self.document_id,
            before=self.ai_output,
            after=corrected,
            actor="Private Reviewer",
            reason="Private correction reason",
            source=CorrectionSource.REVIEWER_EDIT,
        )

        raw = private_dataset_jsonl(self.repository.records)
        summary = sanitized_correction_summary(self.repository.records)
        public_text = json.dumps(summary)

        self.assertIn("Private Reviewer", raw)
        self.assertIn("Acme Logistics", raw)
        self.assertNotIn("Private Reviewer", public_text)
        self.assertNotIn("Acme Logistics", public_text)
        self.assertNotIn(str(self.document_id), public_text)
        self.assertEqual(summary["event_count"], 1)
        self.assertEqual(summary["field_change_counts"], {"vendor_name": 1})

    def test_raw_export_inside_repository_is_limited_to_gitignored_directory(self) -> None:
        repository_root = Path("C:/repo").resolve()

        allowed = assert_private_dataset_path(
            repository_root / "_private_data" / "corrections.jsonl",
            repository_root,
        )

        self.assertEqual(allowed.name, "corrections.jsonl")
        with self.assertRaises(ValueError):
            assert_private_dataset_path(repository_root / "docs" / "raw.jsonl", repository_root)

    def test_sqlite_repository_round_trip_preserves_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SqliteStore(Path(temp_dir) / "corrections.sqlite3")
            repository = SqliteCorrectionEventRepository(store)
            service = CorrectionFeedbackService(repository)
            corrected = InvoiceData(**{**self.ai_output.__dict__, "total": Decimal("110.00")})
            saved = service.capture(
                workspace_id="default",
                document_id=self.document_id,
                before=self.ai_output,
                after=corrected,
                actor="reviewer-1",
                reason="Corrected total",
                source=CorrectionSource.REVIEWER_EDIT,
            )
            loaded = repository.list_for_document("default", self.document_id)
            store.connection.close()

        self.assertEqual(loaded, [saved])


if __name__ == "__main__":
    unittest.main()
