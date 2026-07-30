from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.backoffice.models import TaskPlan, WorkItem
from app.backoffice.sqlite_repositories import (
    SqliteTaskPlanRepository,
    SqliteWorkItemRepository,
)
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.repositories import LeaseLostError
from app.documents.sqlite_repositories import SqliteJobRepository, SqliteStore
from app.documents.sqlite_store import SqliteStore as DirectSqliteStore
from app.documents.status import DocumentStatus
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.main import create_app
from app.providers.contracts import ExtractionResult, ParsedDocument
from app.providers.mock import MockInvoiceExtractor
from app.tests.auth_helpers import session_headers
from app.validation.invoice import ValidationReport


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class SqlitePersistenceTests(unittest.TestCase):
    def test_legacy_module_reexports_sqlite_store(self) -> None:
        self.assertIs(SqliteStore, DirectSqliteStore)

    def test_backoffice_idempotency_keys_are_backfilled_and_duplicates_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "idempotency.sqlite3"
            store = SqliteStore(database_path)
            work_items = SqliteWorkItemRepository(store)
            plans = SqliteTaskPlanRepository(store)
            work_item = work_items.save(
                WorkItem(
                    workspace_id="default",
                    title="Backfill idempotency",
                    idempotency_key="work-key",
                )
            )
            plan = plans.save(
                TaskPlan(
                    workspace_id="default",
                    work_item_id=work_item.id,
                    planner_version="test",
                    idempotency_key="plan-key",
                )
            )
            store.execute(
                "UPDATE backoffice_work_items SET idempotency_key = NULL WHERE id = ?",
                (str(work_item.id),),
            )
            store.execute(
                "UPDATE backoffice_task_plans SET idempotency_key = NULL WHERE id = ?",
                (str(plan.id),),
            )
            store.close()

            reopened = SqliteStore(database_path)
            self.assertEqual(
                reopened.query_one(
                    "SELECT idempotency_key FROM backoffice_work_items WHERE id = ?",
                    (str(work_item.id),),
                )["idempotency_key"],
                "work-key",
            )
            self.assertEqual(
                reopened.query_one(
                    "SELECT idempotency_key FROM backoffice_task_plans WHERE id = ?",
                    (str(plan.id),),
                )["idempotency_key"],
                "plan-key",
            )
            reopened.execute("DROP INDEX idx_backoffice_work_items_idempotency")
            duplicate_repo = SqliteWorkItemRepository(reopened)
            duplicate_repo.save(
                WorkItem(
                    workspace_id="default",
                    title="Duplicate idempotency",
                    idempotency_key="work-key",
                )
            )
            reopened.close()

            with self.assertRaisesRegex(
                RuntimeError,
                "Duplicate backoffice work item idempotency keys",
            ):
                SqliteStore(database_path)

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

    def test_metrics_summary_uses_a_bounded_number_of_queries(self) -> None:
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
                    container.documents.add(
                        DocumentRecord(
                            original_filename=f"invoice-{index:03d}.pdf",
                            storage_key=f"invoice-{index:03d}.pdf",
                            content_type="application/pdf",
                            status=DocumentStatus.NEEDS_REVIEW,
                        )
                    )

                store = container.documents.store
                with (
                    patch.object(store, "query", wraps=store.query) as query_many,
                    patch.object(store, "query_one", wraps=store.query_one) as query_one,
                ):
                    response = TestClient(app).get("/metrics/summary", headers=HEADERS)
            finally:
                container.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["documents_total"], 60)
        self.assertEqual(query_many.call_count + query_one.call_count, 3)

    def test_provider_health_uses_a_bounded_number_of_queries(self) -> None:
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
                    document = container.documents.add(
                        DocumentRecord(
                            original_filename=f"invoice-{index:03d}.pdf",
                            storage_key=f"invoice-{index:03d}.pdf",
                            content_type="application/pdf",
                        )
                    )
                    container.jobs.add(
                        ProcessingJob(
                            document_id=document.id,
                            provider_name="mock_extractor",
                        )
                    )

                store = container.documents.store
                with (
                    patch.object(store, "query", wraps=store.query) as query_many,
                    patch.object(store, "query_one", wraps=store.query_one) as query_one,
                ):
                    response = TestClient(app).get("/providers/health", headers=HEADERS)
            finally:
                container.close()

        self.assertEqual(response.status_code, 200)
        providers = {
            provider["provider_name"]: provider for provider in response.json()["providers"]
        }
        self.assertEqual(providers["mock_extractor"]["observed_runs"], 60)
        self.assertEqual(query_many.call_count + query_one.call_count, 1)

    def test_metrics_duration_precision_matches_memory_and_sqlite(self) -> None:
        observed: list[float] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            for storage_backend in ("memory", "sqlite"):
                settings = Settings(
                    app_env="test",
                    admin_token=TOKEN,
                    upload_root=Path(temp_dir) / storage_backend,
                    max_upload_bytes=1_000,
                    storage_backend=storage_backend,
                    sqlite_path=Path(temp_dir) / f"{storage_backend}.sqlite3",
                )
                app = create_app(settings)
                container = app.state.container
                document = container.documents.add(
                    DocumentRecord(
                        original_filename=f"{storage_backend}.pdf",
                        storage_key=f"{storage_backend}.pdf",
                        content_type="application/pdf",
                    )
                )
                started = datetime(2026, 1, 1, tzinfo=UTC)
                jobs = [
                    ProcessingJob(
                        document_id=document.id,
                        status=ProcessingJobStatus.SUCCEEDED,
                        started_at=started,
                        finished_at=started + timedelta(seconds=1),
                    ),
                    ProcessingJob(
                        document_id=document.id,
                        status=ProcessingJobStatus.SUCCEEDED,
                        started_at=started,
                        finished_at=started + timedelta(seconds=1, microseconds=2_000),
                    ),
                    ProcessingJob(
                        document_id=document.id,
                        status=ProcessingJobStatus.SUCCEEDED,
                        started_at=None,
                        finished_at=None,
                    ),
                    ProcessingJob(
                        document_id=document.id,
                        status=ProcessingJobStatus.SUCCEEDED,
                        started_at=started,
                        finished_at=started - timedelta(seconds=1),
                    ),
                ]
                for job in jobs:
                    container.jobs.add(job)
                observed.append(
                    container.metrics_service.summary(
                        SecurityContext(actor="admin", is_admin=True)
                    )["average_processing_time_ms"]
                )
                container.close()

        self.assertEqual(observed, [1_001.0, 1_001.0])

    def test_operational_jobs_use_a_bounded_number_of_queries(self) -> None:
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
                for index in range(205):
                    document = container.documents.add(
                        DocumentRecord(
                            original_filename=f"invoice-{index:03d}.pdf",
                            storage_key=f"invoice-{index:03d}.pdf",
                            content_type="application/pdf",
                        )
                    )
                    job = ProcessingJob(document_id=document.id)
                    job.fail("injected provider failure")
                    container.jobs.add(job)

                store = container.documents.store
                with (
                    patch.object(store, "query", wraps=store.query) as query_many,
                    patch.object(store, "query_one", wraps=store.query_one) as query_one,
                ):
                    response = TestClient(app).get(
                        "/operations/jobs?failure_page=3&failure_page_size=100",
                        headers=HEADERS,
                    )
            finally:
                container.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["worker"]["failed_jobs"], 205)
        self.assertEqual(len(response.json()["failed_jobs"]), 5)
        self.assertEqual(
            response.json()["failed_jobs_pagination"],
            {
                "page": 3,
                "page_size": 100,
                "returned": 5,
                "total": 205,
                "total_pages": 3,
            },
        )
        self.assertEqual(query_many.call_count + query_one.call_count, 2)

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
            [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
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

    def test_reclaimed_job_fences_the_previous_worker_across_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "doc_intel.sqlite3"
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=database_path,
            )
            first_app = create_app(settings)
            second_app = create_app(settings)
            client = TestClient(first_app)
            client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )

            first_worker_job = first_app.state.container.jobs.claim_next_processable()
            assert first_worker_job is not None
            first_token = first_worker_job.lease_token
            assert first_token is not None
            stale_at = datetime.now(UTC) - timedelta(minutes=10)
            first_app.state.container.documents.store.execute(
                "UPDATE jobs SET updated_at = ? WHERE id = ?",
                (stale_at.isoformat(), str(first_worker_job.id)),
            )

            second_worker_job = second_app.state.container.jobs.claim_next_processable(
                stale_before=datetime.now(UTC) - timedelta(minutes=5)
            )
            assert second_worker_job is not None
            second_token = second_worker_job.lease_token
            assert second_token is not None

            first_renewed = first_app.state.container.jobs.renew_lease(
                first_worker_job.id,
                first_token,
            )
            first_worker_job.succeed()
            with self.assertRaises(LeaseLostError):
                first_app.state.container.jobs.save(
                    first_worker_job,
                    expected_lease_token=first_token,
                )

            second_renewed = second_app.state.container.jobs.renew_lease(
                second_worker_job.id,
                second_token,
            )
            second_worker_job.succeed()
            second_app.state.container.jobs.save(
                second_worker_job,
                expected_lease_token=second_token,
            )
            persisted = first_app.state.container.jobs.get(second_worker_job.id)
            first_app.state.container.documents.store.connection.close()
            second_app.state.container.documents.store.connection.close()

        self.assertNotEqual(first_token, second_token)
        self.assertFalse(first_renewed)
        self.assertTrue(second_renewed)
        self.assertEqual(persisted.status, ProcessingJobStatus.SUCCEEDED)

    def test_stale_worker_cannot_commit_document_results_after_reclaim(self) -> None:
        class BlockingExtractor(MockInvoiceExtractor):
            def __init__(
                self,
                started: threading.Event,
                release: threading.Event,
            ) -> None:
                super().__init__()
                self.started = started
                self.release = release

            def extract_invoice(self, parsed_document: ParsedDocument) -> ExtractionResult:
                self.started.set()
                if not self.release.wait(timeout=5):
                    raise TimeoutError("Test extractor was not released")
                return super().extract_invoice(parsed_document)

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "doc_intel.sqlite3"
            settings = Settings(
                app_env="test",
                admin_token=TOKEN,
                upload_root=Path(temp_dir) / "uploads",
                max_upload_bytes=1000,
                storage_backend="sqlite",
                sqlite_path=database_path,
            )
            first_app = create_app(settings)
            second_app = create_app(settings)
            client = TestClient(first_app)
            upload = client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            ).json()
            document_id = UUID(upload["document"]["id"])

            first_job = first_app.state.container.jobs.claim_next_processable()
            assert first_job is not None
            first_token = first_job.lease_token
            assert first_token is not None
            extraction_started = threading.Event()
            release_extraction = threading.Event()
            first_app.state.container.processing_service.extractor = BlockingExtractor(
                extraction_started,
                release_extraction,
            )
            context = SecurityContext(actor="worker", is_admin=True)
            stale_errors: list[Exception] = []

            def process_with_first_worker() -> None:
                try:
                    first_app.state.container.processing_service.process_job(
                        first_job.id,
                        context,
                        lease_token=first_token,
                    )
                except Exception as exc:
                    stale_errors.append(exc)

            first_thread = threading.Thread(target=process_with_first_worker)
            first_thread.start()
            self.assertTrue(extraction_started.wait(timeout=5))
            stale_at = datetime.now(UTC) - timedelta(minutes=10)
            second_app.state.container.documents.store.execute(
                "UPDATE jobs SET updated_at = ? WHERE id = ?",
                (stale_at.isoformat(), str(first_job.id)),
            )
            second_job = second_app.state.container.jobs.claim_next_processable(
                stale_before=datetime.now(UTC) - timedelta(minutes=5)
            )
            assert second_job is not None
            second_token = second_job.lease_token
            assert second_token is not None
            second_app.state.container.processing_service.process_job(
                second_job.id,
                context,
                lease_token=second_token,
            )

            release_extraction.set()
            first_thread.join(timeout=5)
            self.assertFalse(first_thread.is_alive())
            final_document = second_app.state.container.documents.get(document_id)
            final_job = second_app.state.container.jobs.get(second_job.id)
            final_audits = second_app.state.container.audits.list_for_document(document_id)
            first_app.state.container.documents.store.connection.close()
            second_app.state.container.documents.store.connection.close()

        self.assertEqual(len(stale_errors), 1)
        self.assertIsInstance(stale_errors[0], LeaseLostError)
        self.assertEqual(final_document.status, DocumentStatus.NEEDS_REVIEW)
        self.assertEqual(final_job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(
            sum(event.new_status == DocumentStatus.EXTRACTED for event in final_audits),
            1,
        )
        self.assertEqual(
            sum(event.new_status == DocumentStatus.NEEDS_REVIEW for event in final_audits),
            1,
        )


if __name__ == "__main__":
    unittest.main()
