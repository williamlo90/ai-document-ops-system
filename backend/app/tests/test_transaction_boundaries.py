from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.dependencies import build_container
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.exports.models import ExportBatchRecord, ExportBatchStatus, ExportRunStatus
from app.main import create_app
from app.providers.contracts import ExtractionResult
from app.validation.invoice import ValidationReport


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class TransactionBoundaryTests(unittest.TestCase):
    def test_export_batch_rolls_back_every_document_when_finalization_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            container = build_container(settings)
            try:
                documents = []
                for index in range(2):
                    document = DocumentRecord(
                        original_filename=f"invoice-{index}.pdf",
                        storage_key=f"invoice-{index}.pdf",
                        content_type="application/pdf",
                        status=DocumentStatus.APPROVED,
                    )
                    container.documents.add(document)
                    container.extractions.save(
                        document.id,
                        ExtractionResult(
                            extraction=InvoiceExtraction(
                                data=InvoiceData(
                                    vendor_name=f"Vendor {index}",
                                    invoice_number=f"INV-{index}",
                                    invoice_date=date(2026, 7, 30),
                                    total=Decimal("100.00"),
                                    currency="USD",
                                )
                            ),
                            provider_name="test",
                        ),
                        ValidationReport(issues=()),
                    )
                    documents.append(document)
                batch = ExportBatchRecord(
                    workspace_id="default",
                    document_ids=tuple(document.id for document in documents),
                    destination="csv_download",
                    export_format="csv",
                    created_by="Transaction Test",
                    status=ExportBatchStatus.READY,
                )
                container.export_batches.save_batch(batch)
                original_add = container.documents.add
                write_count = 0

                def fail_second_document_write(document: DocumentRecord) -> DocumentRecord:
                    nonlocal write_count
                    write_count += 1
                    if write_count == 2:
                        raise RuntimeError("injected document finalization failure")
                    return original_add(document)

                with (
                    patch.object(
                        container.documents,
                        "add",
                        side_effect=fail_second_document_write,
                    ),
                    self.assertRaisesRegex(RuntimeError, "Export generation failed"),
                ):
                    container.export_batch_service.execute(
                        context=self._context(),
                        batch_id=batch.id,
                        idempotency_key="transaction-boundary-test",
                    )

                persisted = [container.documents.get(document.id) for document in documents]
                persisted_batch = container.export_batches.get_batch("default", batch.id)
                runs = container.export_batches.list_runs("default")
                self.assertTrue(
                    all(document.status == DocumentStatus.APPROVED for document in persisted)
                )
                self.assertTrue(
                    all(
                        not container.audits.list_for_document(document.id)
                        for document in documents
                    )
                )
                self.assertEqual(persisted_batch.status, ExportBatchStatus.FAILED)
                self.assertEqual(runs[0].status, ExportRunStatus.FAILED)
            finally:
                container.close()

    def test_upload_rolls_back_metadata_and_removes_file_when_job_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            container = build_container(settings)
            try:
                with (
                    patch.object(
                        container.jobs,
                        "add",
                        side_effect=RuntimeError("injected job write failure"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected job write failure"),
                ):
                    container.upload_service.upload_pdf(
                        "invoice.pdf",
                        "application/pdf",
                        [b"%PDF- invoice"],
                        context=self._context(),
                    )

                self.assertEqual(container.documents.list_by_workspace("default"), [])
                self.assertEqual(container.audits.count(), 0)
                self.assertEqual(container.jobs.count(), 0)
                self.assertEqual(list(settings.upload_root.glob("*")), [])
            finally:
                container.close()

    def test_approval_rolls_back_document_and_audit_when_task_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._settings(temp_dir)
            app = create_app(settings)
            client = TestClient(app)
            try:
                upload = client.post(
                    "/documents/upload",
                    headers=HEADERS,
                    files={
                        "file": (
                            "invoice.pdf",
                            b"%PDF- invoice",
                            "application/pdf",
                        )
                    },
                )
                document_id = UUID(upload.json()["document"]["id"])
                process = client.post(
                    f"/documents/{document_id}/process",
                    headers=HEADERS,
                )
                self.assertEqual(process.json()["document"]["status"], "needs_review")
                events_before = [
                    event.event_type
                    for event in app.state.container.audits.list_for_document(document_id)
                ]

                with (
                    patch.object(
                        app.state.container.reviews,
                        "save",
                        side_effect=RuntimeError("injected review write failure"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected review write failure"),
                ):
                    app.state.container.review_service.approve(
                        document_id,
                        context=self._context(),
                    )

                persisted = app.state.container.documents.get(document_id)
                events_after = [
                    event.event_type
                    for event in app.state.container.audits.list_for_document(document_id)
                ]
                self.assertEqual(persisted.status, DocumentStatus.NEEDS_REVIEW)
                self.assertEqual(events_after, events_before)
            finally:
                app.state.container.close()

    def _settings(self, temp_dir: str) -> Settings:
        root = Path(temp_dir)
        return Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=root / "uploads",
            max_upload_bytes=1_000,
            storage_backend="sqlite",
            sqlite_path=root / "doc_intel.sqlite3",
        )

    def _context(self) -> SecurityContext:
        return SecurityContext(
            actor="Transaction Test",
            is_admin=True,
            workspace_id="default",
            user_id="transaction-test",
            role="admin",
        )


if __name__ == "__main__":
    unittest.main()
