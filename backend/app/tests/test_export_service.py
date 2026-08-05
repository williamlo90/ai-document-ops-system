from __future__ import annotations

import csv
import unittest
from dataclasses import FrozenInstanceError
from io import StringIO

from app.documents.models import DocumentRecord
from app.documents.repositories import InMemoryDocumentRepository
from app.documents.status import DocumentStatus
from app.exports.repositories import (
    ExportAlreadyCompleted,
    IdempotencyConflict,
    InMemoryExportRepository,
)
from app.exports.service import ExportNotAllowed, InvoiceExportService
from app.extraction.schemas import InvoiceData
from app.review.models import ReviewRecord
from app.review.repositories import InMemoryReviewRepository


class InvoiceExportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = InMemoryDocumentRepository()
        self.reviews = InMemoryReviewRepository()
        self.exports = InMemoryExportRepository()
        self.service = InvoiceExportService(
            documents=self.documents,
            reviews=self.reviews,
            exports=self.exports,
        )

    def _add_invoice(
        self,
        *,
        status: DocumentStatus = DocumentStatus.APPROVED,
        vendor_name: str = "Acme Logistics",
        invoice_number: str = "INV-001",
    ) -> DocumentRecord:
        document = DocumentRecord(
            "invoice.pdf",
            "private/invoice.pdf",
            "application/pdf",
            workspace_id="finance",
            status=status,
        )
        self.documents.add(document)
        invoice = InvoiceData(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            currency="USD",
        )
        self.reviews.save(ReviewRecord(document.id, invoice, invoice))
        return document

    def test_only_approved_invoice_can_be_exported(self) -> None:
        document = self._add_invoice(status=DocumentStatus.NEEDS_REVIEW)

        with self.assertRaisesRegex(ExportNotAllowed, "Only approved"):
            self.service.export_csv(
                document.id,
                idempotency_key="export-1",
                actor="Maya Chen",
            )

        self.assertEqual(self.exports.list_for_document(document.id), ())

    def test_csv_neutralizes_spreadsheet_formulas_and_records_audit_fields(self) -> None:
        document = self._add_invoice(
            vendor_name="=HYPERLINK(\"https://example.test\")",
            invoice_number=" +cmd|' /C calc'!A0",
        )

        record = self.service.export_csv(
            document.id,
            idempotency_key="export-2",
            actor=" Maya Chen ",
        )
        rows = list(csv.reader(StringIO(record.content.decode("utf-8"))))

        self.assertEqual(rows[1][1], "'=HYPERLINK(\"https://example.test\")")
        self.assertEqual(rows[1][2], "' +cmd|' /C calc'!A0")
        self.assertEqual(record.requested_by, "Maya Chen")
        self.assertEqual(record.workspace_id, "finance")
        self.assertEqual(len(record.content_sha256), 64)
        with self.assertRaises(FrozenInstanceError):
            record.requested_by = "changed"  # type: ignore[misc]

    def test_same_idempotency_key_returns_original_success(self) -> None:
        document = self._add_invoice()

        first = self.service.export_csv(
            document.id,
            idempotency_key="export-3",
            actor="Maya Chen",
        )
        repeated = self.service.export_csv(
            document.id,
            idempotency_key="export-3",
            actor="Another Actor",
        )

        self.assertEqual(repeated, first)
        self.assertEqual(len(self.exports.list_for_document(document.id)), 1)

    def test_new_key_cannot_repeat_successful_export(self) -> None:
        document = self._add_invoice()
        self.service.export_csv(
            document.id,
            idempotency_key="export-4",
            actor="Maya Chen",
        )

        with self.assertRaises(ExportAlreadyCompleted):
            self.service.export_csv(
                document.id,
                idempotency_key="export-5",
                actor="Maya Chen",
            )

    def test_idempotency_key_cannot_be_reused_for_another_invoice(self) -> None:
        first = self._add_invoice(invoice_number="INV-001")
        second = self._add_invoice(invoice_number="INV-002")
        self.service.export_csv(
            first.id,
            idempotency_key="shared-key",
            actor="Maya Chen",
        )

        with self.assertRaises(IdempotencyConflict):
            self.service.export_csv(
                second.id,
                idempotency_key="shared-key",
                actor="Maya Chen",
            )


if __name__ == "__main__":
    unittest.main()
