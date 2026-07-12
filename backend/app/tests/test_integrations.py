from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.security import SecurityContext, UnauthorizedError
from app.documents.repositories import (
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    InMemoryJobRepository,
    InMemoryReviewTaskRepository,
    NotFoundError,
)
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData, InvoiceLineItem
from app.integrations.adapters import MockAccountingAdapter
from app.integrations.models import IntegrationDeliveryError
from app.integrations.services import InvoiceIntegrationService
from app.providers.mock import MockInvoiceExtractor, MockParserProvider
from app.providers.storage import LocalStorageService
from app.review.services import ReviewService


class InvoiceIntegrationTests(unittest.TestCase):
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

    def test_sends_approved_invoice_to_accounting_adapter(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-ERP",
                invoice_date=date(2026, 6, 21),
                subtotal=Decimal("100.00"),
                tax=Decimal("10.00"),
                total=Decimal("110.00"),
                currency="USD",
                line_items=(
                    InvoiceLineItem(
                        description="Freight",
                        quantity=Decimal("2"),
                        unit_price=Decimal("50.00"),
                        amount=Decimal("100.00"),
                    ),
                ),
            )
        )
        adapter = MockAccountingAdapter()

        result = self._integration_service(adapter).send_approved_invoice(
            document.id,
            self.context,
        )

        self.assertEqual(result.integration_result.adapter_name, "mock-accounting")
        self.assertEqual(result.integration_result.external_id, "mock-ap-INV-ERP")
        self.assertEqual(document.status, DocumentStatus.EXPORTED)
        self.assertEqual(adapter.sent_payloads[0].total, "110.00")
        self.assertEqual(adapter.sent_payloads[0].line_items[0].amount, "100.00")
        self.assertEqual(
            [
                event.event_type
                for event in self.audits.list_for_document(document.id)
                if event.event_type.startswith("integration_")
            ],
            ["integration_export_attempted", "integration_export_succeeded"],
        )
        self.assertIn(
            "document_exported",
            [event.event_type for event in self.audits.list_for_document(document.id)],
        )

    def test_failed_delivery_keeps_document_approved_and_audits_failure(self) -> None:
        document = self._process_invoice(
            InvoiceData(
                vendor_name="Acme",
                invoice_number="INV-FAIL",
                invoice_date=date(2026, 6, 21),
                total=Decimal("25.00"),
            )
        )
        adapter = MockAccountingAdapter(fail_invoice_numbers={"INV-FAIL"})

        with self.assertRaises(IntegrationDeliveryError):
            self._integration_service(adapter).send_approved_invoice(document.id, self.context)

        self.assertEqual(document.status, DocumentStatus.APPROVED)
        events = self.audits.list_for_document(document.id)
        self.assertIn("integration_export_attempted", [event.event_type for event in events])
        self.assertIn("integration_export_failed", [event.event_type for event in events])
        self.assertNotIn("document_exported", [event.event_type for event in events])

    def test_rejects_non_approved_documents(self) -> None:
        upload = DocumentUploadService(
            self.storage,
            self.documents,
            self.jobs,
            self.audits,
            self.workflow,
        ).upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )

        with self.assertRaises(InvalidStatusTransition):
            self._integration_service().send_approved_invoice(upload.document.id, self.context)

    def test_integration_is_scoped_by_workspace(self) -> None:
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
        document = self._process_invoice(context=acme_context)

        with self.assertRaises(NotFoundError):
            self._integration_service().send_approved_invoice(document.id, other_context)

        self.assertEqual(document.status, DocumentStatus.APPROVED)

    def test_operator_cannot_send_integration_export(self) -> None:
        document = self._process_invoice()
        operator_context = SecurityContext(actor="operator", is_admin=False, role="operator")

        with self.assertRaises(UnauthorizedError):
            self._integration_service().send_approved_invoice(document.id, operator_context)

    def _integration_service(
        self,
        adapter: MockAccountingAdapter | None = None,
    ) -> InvoiceIntegrationService:
        return InvoiceIntegrationService(
            self.documents,
            self.extractions,
            self.audits,
            self.workflow,
            adapter or MockAccountingAdapter(),
        )

    def _review_service(self) -> ReviewService:
        return ReviewService(
            self.documents,
            self.reviews,
            self.extractions,
            self.audits,
            self.workflow,
        )

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
        document = processor.process_job(result.job.id, context=context)
        self._review_service().approve(document.id, context=context)
        return document


if __name__ == "__main__":
    unittest.main()
