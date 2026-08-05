from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.upload_scanning import ScannerUnavailable, SignaturePdfScanner, UnavailableClamAvScanner, UploadRejected
from app.documents.models import AuditEvent
from app.documents.repositories import InMemoryAuditRepository, InMemoryDocumentRepository, InMemoryJobRepository, InMemoryTransactionManager
from app.documents.services import DocumentUploadService
from app.providers.storage import PrivateDocumentStorage


class FailingAuditRepository(InMemoryAuditRepository):
    def append(self, event: AuditEvent) -> None:
        raise RuntimeError("audit failed")


class ServiceTests(unittest.TestCase):
    def test_upload_creates_document_audit_job_and_private_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            documents = InMemoryDocumentRepository()
            audits = InMemoryAuditRepository()
            jobs = InMemoryJobRepository()
            service = DocumentUploadService(documents=documents, audits=audits, jobs=jobs, transactions=InMemoryTransactionManager(documents, audits, jobs), storage=PrivateDocumentStorage(Path(temp_dir)), scanner=SignaturePdfScanner(), max_bytes=1000)
            result = service.upload(b"%PDF-invoice", filename="invoice.pdf", workspace_id="alpha", actor="Uploader")
            self.assertIsNotNone(documents.get(result.document.id))
            self.assertEqual(len(audits.list_for_document(result.document.id)), 1)
            self.assertIsNotNone(jobs.get(result.job.id))
            self.assertEqual(service.storage.read(result.document.storage_key), b"%PDF-invoice")

    def test_failed_intake_leaves_no_metadata_or_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            documents = InMemoryDocumentRepository()
            tracked_audits = InMemoryAuditRepository()
            jobs = InMemoryJobRepository()
            storage = PrivateDocumentStorage(Path(temp_dir))
            service = DocumentUploadService(documents=documents, audits=FailingAuditRepository(), jobs=jobs, transactions=InMemoryTransactionManager(documents, tracked_audits, jobs), storage=storage, scanner=SignaturePdfScanner(), max_bytes=1000)
            with self.assertRaises(RuntimeError):
                service.upload(b"%PDF-invoice", filename="invoice.pdf", workspace_id="alpha", actor="Uploader")
            self.assertEqual(documents.list_by_workspace("alpha"), [])
            self.assertEqual(list(storage.root.iterdir()), [])

    def test_invalid_pdf_and_unavailable_required_scanner_fail_closed(self) -> None:
        with self.assertRaises(UploadRejected):
            SignaturePdfScanner().scan(b"not-pdf")
        with self.assertRaises(ScannerUnavailable):
            UnavailableClamAvScanner().scan(b"%PDF-invoice")


if __name__ == "__main__":
    unittest.main()
