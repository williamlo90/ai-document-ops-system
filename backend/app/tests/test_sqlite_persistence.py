from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.documents.jobs import ProcessingJobStatus
from app.extraction.schemas import InvoiceData
from app.main import create_app
from app.providers.mock import MockInvoiceExtractor
from app.tests.auth_helpers import session_headers


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class SqlitePersistenceTests(unittest.TestCase):
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
        self.assertEqual([row["version"] for row in migration_rows], [2, 3, 4, 5, 6, 7, 8])
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


if __name__ == "__main__":
    unittest.main()
