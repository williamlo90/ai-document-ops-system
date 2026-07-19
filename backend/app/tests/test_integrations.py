from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
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
from app.integrations.models import (
    IntegrationDeliveryError,
    IntegrationDeliveryRecord,
    IntegrationDeliveryStatus,
    IntegrationIdempotencyConflict,
    IntegrationOutcomeUnknown,
)
from app.integrations.repositories import (
    InMemoryIntegrationDeliveryRepository,
    SqliteIntegrationDeliveryRepository,
)
from app.integrations.services import InvoiceIntegrationService
from app.documents.sqlite_repositories import SqliteStore
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
        self.deliveries = InMemoryIntegrationDeliveryRepository()
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
            idempotency_key="export-inv-erp-001",
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
            self._integration_service(adapter).send_approved_invoice(
                document.id,
                self.context,
                idempotency_key="export-inv-fail-001",
            )

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
            self._integration_service().send_approved_invoice(
                upload.document.id,
                self.context,
                idempotency_key="export-not-approved-001",
            )

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
            self._integration_service().send_approved_invoice(
                document.id,
                other_context,
                idempotency_key="export-wrong-workspace-001",
            )

        self.assertEqual(document.status, DocumentStatus.APPROVED)

    def test_operator_cannot_send_integration_export(self) -> None:
        document = self._process_invoice()
        operator_context = SecurityContext(actor="operator", is_admin=False, role="operator")

        with self.assertRaises(UnauthorizedError):
            self._integration_service().send_approved_invoice(
                document.id,
                operator_context,
                idempotency_key="export-operator-001",
            )

    def test_successful_replay_does_not_send_twice(self) -> None:
        document = self._process_invoice()
        adapter = MockAccountingAdapter()
        service = self._integration_service(adapter)

        first = service.send_approved_invoice(
            document.id, self.context, idempotency_key="stable-replay-key"
        )
        second = service.send_approved_invoice(
            document.id, self.context, idempotency_key="stable-replay-key"
        )

        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(len(adapter.sent_payloads), 1)
        self.assertEqual(
            first.integration_result.external_id, second.integration_result.external_id
        )

    def test_known_retryable_failure_can_retry_with_same_key(self) -> None:
        data = self._valid_invoice("INV-RETRY", Decimal("25.00"))
        document = self._process_invoice(data)
        adapter = MockAccountingAdapter(fail_once_invoice_numbers={"INV-RETRY"})
        service = self._integration_service(adapter)

        with self.assertRaises(IntegrationDeliveryError):
            service.send_approved_invoice(
                document.id, self.context, idempotency_key="retryable-export-key"
            )
        result = service.send_approved_invoice(
            document.id, self.context, idempotency_key="retryable-export-key"
        )

        self.assertEqual(result.delivery.attempt_count, 2)
        self.assertEqual(result.delivery.status, IntegrationDeliveryStatus.SUCCEEDED)
        self.assertEqual(len(adapter.attempted_keys), 2)
        self.assertEqual(len(adapter.sent_payloads), 1)

    def test_unknown_outcome_blocks_resend_until_reconciled(self) -> None:
        data = self._valid_invoice("INV-UNKNOWN", Decimal("25.00"))
        document = self._process_invoice(data)
        adapter = MockAccountingAdapter(unknown_outcome_invoice_numbers={"INV-UNKNOWN"})
        service = self._integration_service(adapter)

        with self.assertRaises(IntegrationDeliveryError):
            service.send_approved_invoice(
                document.id, self.context, idempotency_key="unknown-export-key"
            )
        with self.assertRaises(IntegrationOutcomeUnknown):
            service.send_approved_invoice(
                document.id, self.context, idempotency_key="unknown-export-key"
            )
        reconciled = service.reconcile_delivery(
            idempotency_key="unknown-export-key",
            context=self.context,
            succeeded=True,
            external_id="ledger-123",
            reason="Confirmed in accounting ledger",
        )

        self.assertEqual(len(adapter.attempted_keys), 1)
        self.assertEqual(reconciled.status, IntegrationDeliveryStatus.SUCCEEDED)
        self.assertEqual(document.status, DocumentStatus.EXPORTED)

    def test_key_cannot_be_reused_for_different_document(self) -> None:
        first = self._process_invoice(self._valid_invoice("INV-A", Decimal("1.00")))
        second = self._process_invoice(self._valid_invoice("INV-B", Decimal("2.00")))
        service = self._integration_service()
        service.send_approved_invoice(first.id, self.context, idempotency_key="shared-export-key")

        with self.assertRaises(IntegrationIdempotencyConflict):
            service.send_approved_invoice(
                second.id, self.context, idempotency_key="shared-export-key"
            )

    def test_sqlite_delivery_ledger_survives_repository_recreation(self) -> None:
        db_path = Path(self.temp_dir.name) / "integration-ledger.sqlite3"
        store = SqliteStore(db_path)
        repository = SqliteIntegrationDeliveryRepository(store)
        record = IntegrationDeliveryRecord(
            workspace_id="default",
            document_id=self._process_invoice().id,
            adapter_name="mock-accounting",
            idempotency_key="persistent-export-key",
            payload_hash="abc123",
        )
        repository.reserve(record)
        repository.save(
            replace(
                record,
                status=IntegrationDeliveryStatus.SUCCEEDED,
                external_id="ledger-persisted",
            )
        )
        store.connection.close()

        recreated_store = SqliteStore(db_path)
        recreated = SqliteIntegrationDeliveryRepository(recreated_store).get_by_key(
            "default", "mock-accounting", "persistent-export-key"
        )
        recreated_store.connection.close()

        self.assertIsNotNone(recreated)
        self.assertEqual(recreated.external_id, "ledger-persisted")

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
            self.deliveries,
        )

    def _review_service(self) -> ReviewService:
        return ReviewService(
            self.documents,
            self.reviews,
            self.extractions,
            self.audits,
            self.workflow,
        )

    @staticmethod
    def _valid_invoice(invoice_number: str, total: Decimal) -> InvoiceData:
        return InvoiceData(
            vendor_name="Acme",
            invoice_number=invoice_number,
            invoice_date=date(2026, 6, 21),
            subtotal=total,
            tax=Decimal("0.00"),
            total=total,
            currency="USD",
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
