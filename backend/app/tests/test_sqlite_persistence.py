from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.sqlite_repositories import SqliteJobRepository, SqliteStore
from app.documents.status import DocumentStatus
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.main import create_app
from app.providers.contracts import ExtractionResult
from app.providers.mock import MockInvoiceExtractor
from app.tests.auth_helpers import session_headers
from app.validation.invoice import ValidationReport


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class SqlitePersistenceTests(unittest.TestCase):
    def test_nested_transaction_uses_savepoint_when_inner_failure_is_caught(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SqliteStore(Path(temp_dir) / "doc_intel.sqlite3")
            try:
                store.execute("CREATE TABLE transaction_probe (value TEXT NOT NULL)")
                with store.transaction():
                    store.execute("INSERT INTO transaction_probe VALUES ('outer-before')")
                    try:
                        with store.transaction():
                            store.execute("INSERT INTO transaction_probe VALUES ('inner')")
                            raise ValueError("injected inner failure")
                    except ValueError:
                        pass
                    store.execute("INSERT INTO transaction_probe VALUES ('outer-after')")

                values = [
                    row["value"] for row in store.query("SELECT value FROM transaction_probe")
                ]
            finally:
                store.close()

        self.assertEqual(values, ["outer-before", "outer-after"])

    def test_invoice_page_uses_a_bounded_number_of_queries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1_000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            container = app.state.container
            try:
                for index in range(60):
                    document = DocumentRecord(
                        original_filename=f"invoice-{index:03d}.pdf",
                        storage_key=f"invoice-{index:03d}.pdf",
                        content_type="application/pdf",
                        status=DocumentStatus.NEEDS_REVIEW,
                    )
                    container.documents.add(document)
                    container.extractions.save(
                        document.id,
                        ExtractionResult(
                            extraction=InvoiceExtraction(
                                data=InvoiceData(
                                    vendor_name=f"Vendor {index:03d}",
                                    invoice_number=f"INV-{index:03d}",
                                    invoice_date=date(2026, 7, 1),
                                    total=Decimal("100.00"),
                                    currency="USD",
                                )
                            ),
                            provider_name="test",
                        ),
                        ValidationReport(issues=()),
                    )

                store = container.documents.store
                with (
                    patch.object(store, "query", wraps=store.query) as query_many,
                    patch.object(store, "query_one", wraps=store.query_one) as query_one,
                ):
                    response = TestClient(app).get(
                        "/invoices?page=2&page_size=10&sort=vendor&direction=asc",
                        headers=HEADERS,
                    )
            finally:
                container.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 60)
        self.assertEqual(len(response.json()["items"]), 10)
        self.assertEqual(response.json()["items"][0]["vendor_name"], "Vendor 010")
        self.assertLessEqual(query_many.call_count + query_one.call_count, 7)

    def test_sqlite_enables_concurrency_pragmas_and_query_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SqliteStore(Path(temp_dir) / "doc_intel.sqlite3")
            try:
                pragmas = {
                    "journal_mode": store.query_one("PRAGMA journal_mode")["journal_mode"],
                    "foreign_keys": store.query_one("PRAGMA foreign_keys")["foreign_keys"],
                    "busy_timeout": store.query_one("PRAGMA busy_timeout")["timeout"],
                }
                document_indexes = {
                    row["name"] for row in store.query("PRAGMA index_list('documents')")
                }
                plan = store.query(
                    """
                    EXPLAIN QUERY PLAN
                    SELECT * FROM documents
                    WHERE workspace_id = ? AND status = ?
                    ORDER BY updated_at DESC
                    """,
                    ("default", "needs_review"),
                )
            finally:
                store.close()

        self.assertEqual(pragmas["journal_mode"], "wal")
        self.assertEqual(pragmas["foreign_keys"], 1)
        self.assertGreaterEqual(pragmas["busy_timeout"], 5_000)
        self.assertIn("idx_documents_workspace_status_updated", document_indexes)
        self.assertTrue(
            any("idx_documents_workspace_status_updated" in row["detail"] for row in plan)
        )

    def test_retry_schedule_survives_restart_and_blocks_early_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "doc_intel.sqlite3"
            now = datetime.now(UTC)
            retry_at = now + timedelta(minutes=5)
            store = SqliteStore(path)
            repository = SqliteJobRepository(store)
            job = ProcessingJob(document_id=uuid4())
            job.retry("temporary provider failure", next_attempt_at=retry_at)
            repository.add(job)

            self.assertIsNone(repository.claim_next_processable(now=now))
            store.close()

            reopened_store = SqliteStore(path)
            reopened_repository = SqliteJobRepository(reopened_store)
            try:
                claimed = reopened_repository.claim_next_processable(
                    now=retry_at + timedelta(seconds=1)
                )
            finally:
                reopened_store.close()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, job.id)
        self.assertEqual(claimed.status, ProcessingJobStatus.RUNNING)

    def test_backoffice_aggregate_survives_app_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            client = TestClient(app)
            upload_response = client.post(
                "/documents/upload",
                headers=session_headers(client, actor="William Lo"),
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            document_id = upload_response.json()["document"]["id"]
            client.post(f"/documents/{document_id}/process", headers=HEADERS)
            client.post(f"/review/{document_id}/approve", headers=HEADERS)
            create_response = client.post(
                "/backoffice/work-items",
                headers=HEADERS,
                json={
                    "title": "Export approved invoice",
                    "work_type": "invoice_export",
                    "linked_document_ids": [document_id],
                    "requested_outcome": "Export invoice to accounting",
                },
            )
            work_item_id = create_response.json()["work_item"]["id"]
            plan_response = client.post(
                f"/backoffice/work-items/{work_item_id}/plan",
                headers=HEADERS,
                json={
                    "requested_outcome": "Export invoice to accounting",
                    "evidence_sufficient": True,
                    "approved_for_export": True,
                    "missing_fields": [],
                },
            )
            planned = plan_response.json()["work_item"]
            agent_run_id = planned["current_plan"]["agent_run_id"]
            approval_id = planned["approvals"][0]["id"]
            evaluation_response = client.post(
                "/agentops/backoffice/scenarios/evaluate",
                headers=HEADERS,
                json={
                    "scenario_id": "approved_invoice_export_confirmation",
                    "work_item_id": work_item_id,
                },
            )
            self.assertEqual(evaluation_response.status_code, 200)
            app.state.container.documents.store.connection.close()

            recreated_app = create_app(settings)
            recreated_client = TestClient(recreated_app)
            detail_response = recreated_client.get(
                f"/backoffice/work-items/{work_item_id}", headers=HEADERS
            )
            trace_response = recreated_client.get(f"/agentops/runs/{agent_run_id}", headers=HEADERS)
            evaluations_response = recreated_client.get("/agentops/evaluations", headers=HEADERS)
            approval_response = recreated_client.post(
                f"/backoffice/approvals/{approval_id}/approve",
                headers=HEADERS,
                json={"notes": "Approved after restart."},
            )
            recreated_app.state.container.documents.store.connection.close()

            final_app = create_app(settings)
            final_client = TestClient(final_app)
            final_detail = final_client.get(
                f"/backoffice/work-items/{work_item_id}", headers=HEADERS
            ).json()["work_item"]
            migration_rows = final_app.state.container.documents.store.query(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            workflow_events = final_app.state.container.workflow_events.list_for_document(
                "default", UUID(document_id)
            )
            final_app.state.container.documents.store.connection.close()

        detail = detail_response.json()["work_item"]
        self.assertEqual(detail_response.status_code, 200)
        self.assertIsNotNone(detail["current_plan"])
        self.assertGreaterEqual(len(detail["current_plan"]["steps"]), 2)
        self.assertEqual(len(detail["drafts"]), 1)
        self.assertEqual(len(detail["approvals"]), 1)
        self.assertGreaterEqual(len(detail["policy_decisions"]), 2)
        self.assertEqual(approval_response.json()["approval"]["status"], "approved")
        self.assertEqual(final_detail["approvals"][0]["status"], "approved")
        self.assertEqual(trace_response.status_code, 200)
        self.assertEqual(trace_response.json()["work_item_id"], work_item_id)
        self.assertEqual(
            evaluations_response.json()["evaluations"][0]["scenario_id"],
            "approved_invoice_export_confirmation",
        )
        self.assertTrue(evaluations_response.json()["evaluations"][0]["passed"])
        evaluation_evidence = evaluations_response.json()["evaluations"][0]["evidence"]
        self.assertEqual(evaluation_evidence["expected_document_type"], "invoice")
        self.assertEqual(evaluation_evidence["actual_document_type"], "invoice")
        self.assertEqual(evaluation_evidence["expected_operation_type"], "document_export")
        self.assertEqual(evaluation_evidence["actual_operation_type"], "document_export")
        self.assertTrue(evaluation_evidence["checks"]["document_type"])
        self.assertTrue(evaluation_evidence["checks"]["operation_type"])
        self.assertEqual(
            [row["version"] for row in migration_rows],
            [2, 3, 4, 5, 6, 7, 8, 9, 10],
        )
        self.assertIn("plan_generated", [event.event_type for event in workflow_events])
        self.assertIn("approval_approved", [event.event_type for event in workflow_events])

    def test_document_job_audit_and_extraction_survive_app_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            client = TestClient(app)
            upload_response = client.post(
                "/documents/upload",
                headers=session_headers(client, actor="William Lo"),
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            document_id = upload_response.json()["document"]["id"]
            process_response = client.post(f"/documents/{document_id}/process", headers=HEADERS)
            self.assertEqual(process_response.json()["document"]["status"], "needs_review")
            app.state.container.documents.store.connection.close()

            recreated_app = create_app(settings)
            recreated_client = TestClient(recreated_app)
            detail_response = recreated_client.get(f"/documents/{document_id}", headers=HEADERS)
            metrics_response = recreated_client.get("/metrics/summary", headers=HEADERS)
            recreated_app.state.container.documents.store.connection.close()

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["document"]["status"], "needs_review")
        self.assertEqual(detail_response.json()["document"]["submitted_by"], "William Lo")
        self.assertGreater(detail_response.json()["document"]["size_bytes"], 0)
        self.assertEqual(detail_response.json()["extraction"]["data"]["invoice_number"], "INV-001")
        self.assertGreaterEqual(len(detail_response.json()["audit_events"]), 4)
        self.assertEqual(metrics_response.json()["documents_total"], 1)
        self.assertEqual(metrics_response.json()["jobs_total"], 1)

    def test_needs_review_validation_issues_survive_app_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            app.state.container.processing_service.extractor = MockInvoiceExtractor(
                InvoiceData(
                    vendor_name="Acme",
                    invoice_number="INV-REVIEW",
                    invoice_date=date(2026, 6, 18),
                    total=Decimal("0"),
                )
            )
            client = TestClient(app)
            upload_response = client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            document_id = upload_response.json()["document"]["id"]
            process_response = client.post(f"/documents/{document_id}/process", headers=HEADERS)
            self.assertEqual(process_response.json()["document"]["status"], "needs_review")
            app.state.container.documents.store.connection.close()

            recreated_app = create_app(settings)
            recreated_client = TestClient(recreated_app)
            detail_response = recreated_client.get(f"/documents/{document_id}", headers=HEADERS)
            queue_response = recreated_client.get("/review/queue", headers=HEADERS)
            recreated_app.state.container.documents.store.connection.close()

        detail = detail_response.json()
        self.assertEqual(detail["document"]["status"], "needs_review")
        self.assertEqual(detail["extraction"]["validation"][0]["code"], "invalid_total")
        self.assertEqual(queue_response.json()[0]["id"], document_id)

    def test_claimed_sqlite_job_is_not_claimed_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            client = TestClient(app)
            client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )

            first_claim = app.state.container.jobs.claim_next_processable()
            second_claim = app.state.container.jobs.claim_next_processable()
            app.state.container.documents.store.connection.close()

        self.assertIsNotNone(first_claim)
        self.assertEqual(first_claim.status, ProcessingJobStatus.RUNNING)
        self.assertIsNone(second_claim)

    def test_expired_sqlite_job_is_reclaimed_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
            )
            app = create_app(settings)
            client = TestClient(app)
            client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            first_claim = app.state.container.jobs.claim_next_processable()
            assert first_claim is not None
            first_claim.updated_at = datetime.now(UTC) - timedelta(minutes=10)
            app.state.container.jobs.save(first_claim)

            reclaimed = app.state.container.jobs.claim_next_processable(
                stale_before=datetime.now(UTC) - timedelta(minutes=5)
            )
            concurrent_claim = app.state.container.jobs.claim_next_processable(
                stale_before=datetime.now(UTC) - timedelta(minutes=5)
            )
            app.state.container.documents.store.connection.close()

        self.assertIsNotNone(reclaimed)
        assert reclaimed is not None
        self.assertEqual(reclaimed.status, ProcessingJobStatus.RUNNING)
        self.assertEqual(reclaimed.attempt_count, 2)
        self.assertEqual(reclaimed.error_message, "worker_lease_expired")
        self.assertIsNone(concurrent_claim)


if __name__ == "__main__":
    unittest.main()
