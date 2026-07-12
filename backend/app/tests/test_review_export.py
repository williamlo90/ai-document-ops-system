from __future__ import annotations

import tempfile
import unittest
import csv
from io import StringIO
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.security import SecurityContext, UnauthorizedError
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    InMemoryJobRepository,
    InMemoryReviewTaskRepository,
)
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.exports.services import InvoiceExportService
from app.extraction.schemas import InvoiceData
from app.providers.mock import MockInvoiceExtractor, MockParserProvider
from app.providers.storage import LocalStorageService
from app.review.services import ReviewService


class ReviewAndExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LocalStorageService(Path(self.temp_dir.name), max_upload_bytes=1000)
        self.documents = InMemoryDocumentRepository()
        self.jobs = InMemoryJobRepository()
        self.audits = InMemoryAuditRepository()
        self.extractions = InMemoryExtractionRepository()
        self.reviews = InMemoryReviewTaskRepository()
        self.workflow = DocumentWorkflowService()
        self.context = SecurityContext(actor="tester", is_admin=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_review_and_approve_needs_review_document(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-REVIEW",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )
        service = self._review_service()

        corrected = InvoiceData(
            vendor_name="Acme Corrected",
            invoice_number="INV-REVIEW",
            invoice_date=date(2026, 6, 18),
            total=Decimal("25.00"),
        )
        task = service.save_review(
            document.id,
            notes="fixed total manually",
            context=self.context,
            corrected_data=corrected,
        )
        approved = service.approve(document.id, context=self.context)

        self.assertEqual(task.reviewer_notes, "fixed total manually")
        self.assertEqual(approved.status, "approved")
        self.assertEqual(document.status, DocumentStatus.APPROVED)
        self.assertEqual(
            self.extractions.get_for_document(
                document.id
            ).extraction_result.extraction.data.vendor_name,
            "Acme Corrected",
        )
        self.assertIn(
            "extraction_updated",
            [event.event_type for event in self.audits.list_for_document(document.id)],
        )

    def test_reject_needs_review_document(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-REJECT",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )
        service = self._review_service()

        task = service.reject(document.id, notes="not an invoice", context=self.context)

        self.assertEqual(task.status, "rejected")
        self.assertEqual(document.status, DocumentStatus.REJECTED)
        self.assertEqual(
            self.audits.list_for_document(document.id)[-1].event_type,
            "document_rejected",
        )

    def test_cannot_approve_non_reviewable_document(self) -> None:
        document = self._process_invoice()

        with self.assertRaises(InvalidStatusTransition):
            self._review_service().approve(document.id, context=self.context)

    def test_reject_failure_does_not_mutate_existing_approved_task(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-MUTATION",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )
        service = self._review_service()
        service.save_review(document.id, notes="original notes", context=self.context)
        service.approve(document.id, context=self.context)
        before_events = list(self.audits.list_for_document(document.id))

        with self.assertRaises(InvalidStatusTransition):
            service.reject(document.id, notes="should not save", context=self.context)

        task = self.reviews.get_for_document(document.id)
        self.assertEqual(task.reviewer_notes, "original notes")
        self.assertEqual(task.status, "approved")
        self.assertEqual(document.status, DocumentStatus.APPROVED)
        self.assertEqual(self.audits.list_for_document(document.id), before_events)

    def test_review_requires_admin_context(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-SEC",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )

        with self.assertRaises(UnauthorizedError):
            self._review_service().save_review(
                document.id,
                notes="nope",
                context=SecurityContext(actor="viewer", is_admin=False),
            )

    def test_reviewer_role_can_save_review(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-ROLE",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )
        reviewer_context = SecurityContext(
            actor="reviewer-1",
            is_admin=False,
            role="reviewer",
        )

        task = self._review_service().save_review(
            document.id,
            notes="reviewed",
            context=reviewer_context,
        )

        self.assertEqual(task.reviewed_by, "reviewer-1")

    def test_operator_role_cannot_save_review(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-OP",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )
        operator_context = SecurityContext(
            actor="operator-1",
            is_admin=False,
            role="operator",
        )

        with self.assertRaises(UnauthorizedError):
            self._review_service().save_review(
                document.id,
                notes="not allowed",
                context=operator_context,
            )

    def test_review_queue_is_scoped_by_workspace(self) -> None:
        acme_context = SecurityContext(
            actor="acme-admin",
            is_admin=True,
            workspace_id="acme",
            user_id="acme-admin",
            role="admin",
        )
        other_context = SecurityContext(
            actor="other-admin",
            is_admin=True,
            workspace_id="other",
            user_id="other-admin",
            role="admin",
        )
        acme_document = self._process_invoice(
            InvoiceData(invoice_number="INV-A", total=Decimal("0")),
            context=acme_context,
        )
        self._process_invoice(
            InvoiceData(invoice_number="INV-B", total=Decimal("0")),
            context=other_context,
        )

        queue = self._review_service().list_queue(acme_context)

        self.assertEqual([document.id for document in queue], [acme_document.id])

    def test_export_approved_only_and_escape_dangerous_strings(self) -> None:
        approved = self._process_invoice(
            InvoiceData(
                vendor_name="=Acme, Inc.\nNorth",
                invoice_number='\t=INV-"001"',
                invoice_date=date(2026, 6, 18),
                due_date=date(2026, 7, 18),
                subtotal=Decimal("100.00"),
                tax=Decimal("10.00"),
                total=Decimal("110.00"),
                currency="USD",
            )
        )
        needs_review = self._process_invoice(
            InvoiceData(
                vendor_name="Bad",
                invoice_number="INV-BAD",
                invoice_date=date(2026, 6, 18),
                total=Decimal("0"),
            )
        )

        csv_text = InvoiceExportService(
            self.documents,
            self.extractions,
            self.audits,
            self.workflow,
        ).export_approved_csv(context=self.context)

        self.assertIn(str(approved.id), csv_text)
        self.assertNotIn(str(needs_review.id), csv_text)
        rows = list(csv.DictReader(StringIO(csv_text)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["vendor_name"], "'=Acme, Inc.\nNorth")
        self.assertEqual(rows[0]["invoice_number"], '\'\t=INV-"001"')
        self.assertEqual(approved.status, DocumentStatus.EXPORTED)
        self.assertEqual(needs_review.status, DocumentStatus.NEEDS_REVIEW)

    def test_export_is_scoped_by_workspace(self) -> None:
        acme_context = SecurityContext(
            actor="acme-admin",
            is_admin=True,
            workspace_id="acme",
            user_id="acme-admin",
            role="admin",
        )
        other_context = SecurityContext(
            actor="other-admin",
            is_admin=True,
            workspace_id="other",
            user_id="other-admin",
            role="admin",
        )
        acme_document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-ACME",
                invoice_date=date(2026, 6, 18),
                total=Decimal("25.00"),
            ),
            context=acme_context,
        )
        other_document = self._process_invoice(
            InvoiceData(
                vendor_name="Other",
                invoice_number="INV-OTHER",
                invoice_date=date(2026, 6, 18),
                total=Decimal("25.00"),
            ),
            context=other_context,
        )

        csv_text = InvoiceExportService(
            self.documents,
            self.extractions,
            self.audits,
            self.workflow,
        ).export_approved_csv(context=acme_context)

        self.assertIn(str(acme_document.id), csv_text)
        self.assertNotIn(str(other_document.id), csv_text)
        self.assertEqual(acme_document.status, DocumentStatus.EXPORTED)
        self.assertEqual(other_document.status, DocumentStatus.APPROVED)

    def test_export_second_run_excludes_already_exported_documents(self) -> None:
        approved = self._process_invoice()
        export_service = InvoiceExportService(
            self.documents,
            self.extractions,
            self.audits,
            self.workflow,
        )

        first_csv = export_service.export_approved_csv(context=self.context)
        second_csv = export_service.export_approved_csv(context=self.context)

        self.assertIn(str(approved.id), first_csv)
        self.assertNotIn(str(approved.id), second_csv)
        self.assertEqual(
            second_csv,
            ",".join(
                [
                    "document_id",
                    "vendor_name",
                    "invoice_number",
                    "invoice_date",
                    "due_date",
                    "subtotal",
                    "tax",
                    "total",
                    "currency",
                ]
            )
            + "\n",
        )

    def test_prediction_json_includes_extracted_documents_without_changing_status(self) -> None:
        approved = self._process_invoice()
        queued = DocumentRecord(
            original_filename="queued.pdf",
            storage_key="queued.pdf",
            content_type="application/pdf",
            status=DocumentStatus.QUEUED,
        )
        self.documents.add(queued)

        json_text = InvoiceExportService(
            self.documents,
            self.extractions,
            self.audits,
            self.workflow,
        ).export_predictions_json(context=self.context)

        self.assertIn(str(approved.id), json_text)
        self.assertIn("INV-001", json_text)
        self.assertNotIn(str(queued.id), json_text)
        self.assertEqual(approved.status, DocumentStatus.APPROVED)

    def test_export_does_not_mark_any_document_if_row_collection_fails(self) -> None:
        first = self._process_invoice()
        second = self._process_invoice()
        self.extractions.records.pop(second.id)

        with self.assertRaises(Exception):
            InvoiceExportService(
                self.documents,
                self.extractions,
                self.audits,
                self.workflow,
            ).export_approved_csv(context=self.context)

        self.assertEqual(first.status, DocumentStatus.APPROVED)
        self.assertEqual(second.status, DocumentStatus.APPROVED)

    def _process_invoice(
        self,
        invoice_data: InvoiceData | None = None,
        context: SecurityContext | None = None,
    ):
        context = context or self.context
        upload = DocumentUploadService(
            self.storage,
            self.documents,
            self.jobs,
            self.audits,
            self.workflow,
        )
        result = upload.upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=context,
        )
        processor = DocumentProcessingService(
            self.storage,
            self.documents,
            self.jobs,
            self.audits,
            self.extractions,
            self.workflow,
            MockParserProvider(),
            MockInvoiceExtractor(invoice_data),
        )
        return processor.process_job(result.job.id, context=context)

    def _review_service(self) -> ReviewService:
        return ReviewService(
            self.documents,
            self.reviews,
            self.extractions,
            self.audits,
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
