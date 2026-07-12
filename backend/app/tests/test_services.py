from __future__ import annotations

import tempfile
import unittest
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.core.security import SecurityContext, UnauthorizedError
from app.documents.jobs import ProcessingJobStatus
from app.documents.repositories import (
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    InMemoryJobRepository,
)
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.status import DocumentStatus
from app.documents.worker import DocumentProcessingWorker
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData
from app.providers.contracts import DocumentSource, ProviderError
from app.providers.mock import MockInvoiceExtractor, MockParserProvider
from app.providers.storage import LocalStorageService


class DocumentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = LocalStorageService(Path(self.temp_dir.name), max_upload_bytes=1000)
        self.documents = InMemoryDocumentRepository()
        self.jobs = InMemoryJobRepository()
        self.audits = InMemoryAuditRepository()
        self.extractions = InMemoryExtractionRepository()
        self.workflow = DocumentWorkflowService()
        self.context = SecurityContext(actor="tester", is_admin=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_upload_creates_document_job_and_audit_events(self) -> None:
        upload = self._upload_service()

        with self.assertLogs("docintel.operations", level="INFO") as logs:
            result = upload.upload_pdf(
                "invoice.pdf",
                "application/pdf",
                [b"%PDF- invoice"],
                context=self.context,
            )

        self.assertEqual(result.document.status, DocumentStatus.QUEUED)
        self.assertEqual(result.document.workspace_id, "default")
        self.assertEqual(result.job.document_id, result.document.id)
        self.assertEqual(
            [event.event_type for event in self.audits.list_for_document(result.document.id)],
            ["document_uploaded", "processing_queued"],
        )
        payload = json.loads(logs.output[0].split("INFO:docintel.operations:", 1)[1])
        self.assertEqual(payload["event_type"], "document_uploaded")
        self.assertEqual(payload["document_id"], str(result.document.id))
        self.assertNotIn("%PDF-", logs.output[0])

    def test_process_valid_invoice_waits_for_reviewer_approval(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service()

        with self.assertLogs("docintel.operations", level="INFO") as logs:
            document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.NEEDS_REVIEW)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertFalse(
            self.extractions.get_for_document(document.id).validation_report.has_errors
        )
        self.assertIn("processing_started", logs.output[0])
        self.assertIn("processing_succeeded", logs.output[-1])
        self.assertIn(
            "Invoice is ready for reviewer approval.",
            [event.payload_summary for event in self.audits.list_for_document(document.id)],
        )

    def test_process_invalid_invoice_routes_to_review(self) -> None:
        invalid_invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-002",
            invoice_date=date(2026, 6, 18),
            total=Decimal("0"),
        )
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(extractor=MockInvoiceExtractor(invalid_invoice))

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.NEEDS_REVIEW)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertTrue(self.extractions.get_for_document(document.id).validation_report.has_errors)

    def test_provider_error_fails_document_and_job_safely(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(parser=FailingParser())

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(upload_result.job.error_message, "provider_error:failing_parser")

    def test_retryable_provider_error_requeues_document_and_job(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(parser=RetryableFailingParser())

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.QUEUED)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.RETRYING)
        self.assertEqual(upload_result.job.attempt_count, 1)
        self.assertEqual(upload_result.job.error_message, "provider_error:retryable_parser")

    def test_retrying_job_can_succeed_on_later_attempt(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        parser = FlakyParser()
        processor = self._processing_service(parser=parser)

        first_document = processor.process_job(upload_result.job.id, context=self.context)
        self.assertEqual(first_document.status, DocumentStatus.QUEUED)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.RETRYING)

        second_document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(second_document.status, DocumentStatus.NEEDS_REVIEW)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(upload_result.job.attempt_count, 2)

    def test_retryable_provider_error_dead_letters_after_limit(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(
            parser=RetryableFailingParser(),
            max_processing_attempts=1,
        )

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.DEAD_LETTER)
        self.assertEqual(upload_result.job.attempt_count, 1)

    def test_empty_parser_text_fails_document_and_job_safely(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(parser=MockParserProvider(text=""))

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(upload_result.job.error_message, "provider_error:mock_parser")

    def test_non_provider_exception_stores_class_name_only(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(extractor=ExplodingExtractor())

        document = processor.process_job(upload_result.job.id, context=self.context)

        self.assertEqual(document.status, DocumentStatus.FAILED)
        self.assertEqual(upload_result.job.error_message, "RuntimeError")

    def test_worker_processes_next_queued_job(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        worker = DocumentProcessingWorker(self.jobs, self._processing_service())

        document = worker.run_once(context=self.context)

        self.assertIsNotNone(document)
        self.assertEqual(document.id, upload_result.document.id)
        self.assertEqual(document.status, DocumentStatus.NEEDS_REVIEW)

    def test_worker_claims_job_before_processing(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        claimed = self.jobs.claim_next_processable()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, upload_result.job.id)
        self.assertEqual(upload_result.job.status, ProcessingJobStatus.RUNNING)

    def test_claimed_job_is_not_claimed_twice(self) -> None:
        self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )

        first_claim = self.jobs.claim_next_processable()
        second_claim = self.jobs.claim_next_processable()

        self.assertIsNotNone(first_claim)
        self.assertIsNone(second_claim)

    def test_worker_returns_none_when_no_processable_job_exists(self) -> None:
        worker = DocumentProcessingWorker(self.jobs, self._processing_service())

        document = worker.run_once(context=self.context)

        self.assertIsNone(document)

    def test_failed_processing_creates_single_failed_audit_event(self) -> None:
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=self.context,
        )
        processor = self._processing_service(parser=FailingParser())

        processor.process_job(upload_result.job.id, context=self.context)

        events = self.audits.list_for_document(upload_result.document.id)
        self.assertEqual(
            [event.event_type for event in events],
            ["document_uploaded", "processing_queued", "processing_started", "processing_failed"],
        )

    def test_invalid_upload_has_no_repository_side_effects(self) -> None:
        upload = self._upload_service()

        with self.assertRaises(Exception):
            upload.upload_pdf(
                "invoice.txt",
                "application/pdf",
                [b"%PDF- invoice"],
                context=self.context,
            )

        self.assertEqual(self.documents.records, {})
        self.assertEqual(self.jobs.records, {})
        self.assertEqual(self.audits.records, [])

    def test_upload_requires_admin_context(self) -> None:
        upload = self._upload_service()

        with self.assertRaises(UnauthorizedError):
            upload.upload_pdf(
                "invoice.pdf",
                "application/pdf",
                [b"%PDF- invoice"],
                context=SecurityContext(actor="viewer", is_admin=False),
            )

    def test_processing_rejects_cross_workspace_document(self) -> None:
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
        upload_result = self._upload_service().upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF- invoice"],
            context=acme_context,
        )

        with self.assertRaises(KeyError):
            self._processing_service().process_job(upload_result.job.id, context=other_context)

    def _upload_service(self) -> DocumentUploadService:
        return DocumentUploadService(
            storage=self.storage,
            documents=self.documents,
            jobs=self.jobs,
            audits=self.audits,
            workflow=self.workflow,
        )

    def _processing_service(
        self,
        parser: MockParserProvider | None = None,
        extractor: MockInvoiceExtractor | None = None,
        max_processing_attempts: int = 3,
    ) -> DocumentProcessingService:
        return DocumentProcessingService(
            storage=self.storage,
            documents=self.documents,
            jobs=self.jobs,
            audits=self.audits,
            extractions=self.extractions,
            workflow=self.workflow,
            parser=parser or MockParserProvider(),
            extractor=extractor or MockInvoiceExtractor(),
            max_processing_attempts=max_processing_attempts,
        )


class FailingParser:
    provider_name = "failing_parser"

    def parse(self, source: DocumentSource):
        raise ProviderError("secret raw document text should not be stored", self.provider_name)


class RetryableFailingParser:
    provider_name = "retryable_parser"

    def parse(self, source: DocumentSource):
        raise ProviderError(
            "temporary provider outage",
            self.provider_name,
            retryable=True,
        )


class FlakyParser:
    provider_name = "flaky_parser"

    def __init__(self) -> None:
        self.calls = 0

    def parse(self, source: DocumentSource):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError(
                "temporary provider outage",
                self.provider_name,
                retryable=True,
            )
        return MockParserProvider().parse(source)


class ExplodingExtractor:
    provider_name = "exploding_extractor"

    def extract_invoice(self, parsed_document):
        raise RuntimeError("secret raw OCR text should not be stored")


if __name__ == "__main__":
    unittest.main()
