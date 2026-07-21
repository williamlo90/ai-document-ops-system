from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.extraction.schemas import SCHEMA_VERSION
from app.main import create_app
from app.providers.mock import MockParserProvider
from app.providers.contracts import ProviderError
from app.tests.auth_helpers import session_headers


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_health_does_not_require_token(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_reports_database_and_storage_checks(self) -> None:
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["checks"]["database"], "ok")
        self.assertEqual(response.json()["checks"]["storage"], "ok")

    def test_provider_health_reports_runtime_provider_and_evidence_state(self) -> None:
        response = self.client.get("/providers/health", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overall_status"], "healthy")
        self.assertEqual(
            [provider["role"] for provider in payload["providers"]],
            ["parser", "extractor"],
        )
        self.assertTrue(all(provider["configuration_ready"] for provider in payload["providers"]))
        self.assertTrue(all(provider["evidence"] for provider in payload["providers"]))

    def test_local_document_download_contract_uses_authenticated_content_url(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]

        response = self.client.get(f"/documents/{document_id}/download-url", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["signed"])
        self.assertEqual(response.json()["url"], f"/documents/{document_id}/content")

    def test_upload_requires_admin_token(self) -> None:
        response = self.client.post(
            "/documents/upload",
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")

    def test_legacy_ui_urls_redirect_to_react(self) -> None:
        destinations = {
            "/ui": "/",
            "/ui/agentops": "/?technical=runs",
            "/ui/benchmarks": "/?technical=evaluation",
            "/ui/backoffice": "/?technical=approvals",
        }
        for path, destination in destinations.items():
            with self.subTest(path=path):
                response = self.client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 307)
                self.assertEqual(response.headers["location"], destination)

    def test_protected_routes_reject_missing_or_wrong_token(self) -> None:
        document_id = uuid4()
        protected_requests = (
            ("get", "/documents"),
            ("get", f"/documents/{document_id}"),
            ("post", f"/documents/{document_id}/process"),
            ("get", "/review/queue"),
            ("post", f"/review/{document_id}/save"),
            ("post", f"/review/{document_id}/approve"),
            ("post", f"/review/{document_id}/reject"),
            ("get", "/exports/invoices.csv"),
            ("get", "/exports/predictions.json"),
            ("post", f"/integrations/accounting/documents/{document_id}/export"),
            ("get", "/metrics/summary"),
            ("get", "/evaluation/dashboard"),
            ("post", "/evaluation/runs"),
            ("post", "/agent/copilot"),
        )

        for method_name, path in protected_requests:
            with self.subTest(method=method_name, path=path):
                response = self.client.request(
                    method_name.upper(),
                    path,
                    headers={"X-Admin-Token": "wrong"},
                    json={},
                )

                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], "Unauthorized")

    def test_reviewer_role_can_use_review_api_without_admin_access(self) -> None:
        upload_response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        reviewer_headers = session_headers(
            self.client,
            actor="reviewer-1",
            role="reviewer",
        )

        queue_response = self.client.get("/review/queue", headers=reviewer_headers)
        approve_response = self.client.post(
            f"/review/{document_id}/approve",
            headers=reviewer_headers,
        )

        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()[0]["id"], document_id)
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["review_task"]["status"], "approved")

    def test_reviewer_cannot_review_cross_workspace_document(self) -> None:
        acme_headers = session_headers(
            self.client,
            actor="acme-admin",
            workspace_id="acme",
        )
        other_reviewer_headers = session_headers(
            self.client,
            actor="other-reviewer",
            workspace_id="other",
            role="reviewer",
        )
        upload_response = self.client.post(
            "/documents/upload",
            headers=acme_headers,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=acme_headers)

        queue_response = self.client.get("/review/queue", headers=other_reviewer_headers)
        approve_response = self.client.post(
            f"/review/{document_id}/approve",
            headers=other_reviewer_headers,
        )

        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json(), [])
        self.assertEqual(approve_response.status_code, 404)

    def test_operator_role_cannot_use_review_api(self) -> None:
        upload_response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        operator_headers = session_headers(
            self.client,
            actor="operator-1",
            role="operator",
        )

        queue_response = self.client.get("/review/queue", headers=operator_headers)
        approve_response = self.client.post(
            f"/review/{document_id}/approve",
            headers=operator_headers,
        )

        self.assertEqual(queue_response.status_code, 403)
        self.assertEqual(approve_response.status_code, 403)

    def test_upload_validation_errors_are_bad_request(self) -> None:
        cases = (
            ("invoice.txt", b"%PDF- invoice", "application/pdf"),
            ("invoice.pdf", b"%PDF- invoice", "text/plain"),
            ("invoice.pdf", b"", "application/pdf"),
            ("invoice.pdf", b"not a pdf", "application/pdf"),
            ("invoice.pdf", b"%PDF-" + (b"x" * 1200), "application/pdf"),
        )

        for filename, content, content_type in cases:
            with self.subTest(filename=filename, content_type=content_type):
                response = self.client.post(
                    "/documents/upload",
                    headers=HEADERS,
                    files={"file": (filename, content, content_type)},
                )

                self.assertEqual(response.status_code, 400)

    def test_missing_upload_field_is_validation_error(self) -> None:
        response = self.client.post("/documents/upload", headers=HEADERS)

        self.assertEqual(response.status_code, 422)

    def test_upload_process_list_detail_metrics_and_export(self) -> None:
        upload_response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 200)
        document_id = upload_response.json()["document"]["id"]
        self.assertEqual(upload_response.json()["document"]["document_type"], "invoice")
        self.assertEqual(
            upload_response.json()["document"]["supported_extraction_schema"],
            SCHEMA_VERSION,
        )

        process_response = self.client.post(
            f"/documents/{document_id}/process",
            headers=HEADERS,
        )
        self.assertEqual(process_response.status_code, 200)
        self.assertEqual(process_response.json()["document"]["status"], "needs_review")

        list_response = self.client.get("/documents", headers=HEADERS)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["document"]["document_type"], "invoice")
        self.assertEqual(detail_response.json()["extraction"]["document_type"], "invoice")
        self.assertEqual(detail_response.json()["extraction"]["schema_version"], SCHEMA_VERSION)
        self.assertEqual(detail_response.json()["extraction"]["data"]["invoice_number"], "INV-001")

        metrics_response = self.client.get("/metrics/summary", headers=HEADERS)
        self.assertEqual(metrics_response.status_code, 200)
        metrics = metrics_response.json()
        self.assertEqual(metrics["documents_total"], 1)
        self.assertEqual(metrics["queue"]["succeeded"], 1)
        self.assertEqual(metrics["provider"]["by_provider"]["mock_extractor"], 1)
        self.assertEqual(metrics["review"]["queue_count"], 1)
        self.assertEqual(metrics["review"]["approved_count"], 0)
        self.assertEqual(metrics["cost"]["processed_documents"], 1)
        self.assertIn("average_processing_time_ms", metrics)
        self.assertIsInstance(metrics["average_processing_time_ms"], (int, float))

        export_response = self.client.get("/exports/invoices.csv", headers=HEADERS)
        self.assertNotIn(document_id, export_response.text)

        approve_response = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)
        self.assertEqual(approve_response.status_code, 200)
        decision = approve_response.json()["decision"]
        self.assertEqual(decision["status"], "approved")
        self.assertEqual(decision["actor"], "Administrator")
        self.assertIsNotNone(decision["recorded_at"])
        self.assertGreaterEqual(decision["audit_event_count"], 1)
        self.assertEqual(decision["export_eligibility"], "eligible")

        export_response = self.client.get("/exports/invoices.csv", headers=HEADERS)
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("text/csv", export_response.headers["content-type"])
        self.assertEqual(
            export_response.headers["content-disposition"],
            'attachment; filename="invoices.csv"',
        )
        self.assertEqual(export_response.headers["cache-control"], "no-store")
        self.assertIn(document_id, export_response.text)

        repeat_export_response = self.client.get("/exports/invoices.csv", headers=HEADERS)
        self.assertEqual(repeat_export_response.status_code, 200)
        self.assertNotIn(document_id, repeat_export_response.text)

    def test_accounting_integration_endpoint_exports_approved_document(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        response = self.client.post(
            f"/integrations/accounting/documents/{document_id}/export",
            headers={**HEADERS, "Idempotency-Key": "api-export-inv-001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["status"], "exported")
        self.assertEqual(response.json()["integration"]["adapter_name"], "mock-accounting")
        self.assertEqual(response.json()["integration"]["external_id"], "mock-ap-INV-001")

        replay = self.client.post(
            f"/integrations/accounting/documents/{document_id}/export",
            headers={**HEADERS, "Idempotency-Key": "api-export-inv-001"},
        )
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["integration"]["replayed"])

    def test_accounting_integration_requires_idempotency_key(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        response = self.client.post(
            f"/integrations/accounting/documents/{document_id}/export",
            headers=HEADERS,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("Idempotency-Key", response.json()["detail"])

    def test_api_document_access_is_scoped_by_workspace(self) -> None:
        acme_headers = session_headers(
            self.client,
            actor="acme-admin",
            workspace_id="acme",
        )
        other_headers = session_headers(
            self.client,
            actor="other-admin",
            workspace_id="other",
        )

        upload_response = self.client.post(
            "/documents/upload",
            headers=acme_headers,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]

        acme_list = self.client.get("/documents", headers=acme_headers)
        other_list = self.client.get("/documents", headers=other_headers)
        other_detail = self.client.get(f"/documents/{document_id}", headers=other_headers)
        other_process = self.client.post(f"/documents/{document_id}/process", headers=other_headers)

        self.assertEqual(acme_list.status_code, 200)
        self.assertEqual(acme_list.json()[0]["workspace_id"], "acme")
        self.assertEqual(other_list.status_code, 200)
        self.assertEqual(other_list.json(), [])
        self.assertEqual(other_detail.status_code, 404)
        self.assertEqual(other_process.status_code, 404)

    def test_metrics_are_scoped_by_workspace(self) -> None:
        acme_headers = session_headers(
            self.client,
            actor="acme-admin",
            workspace_id="acme",
        )
        other_headers = session_headers(
            self.client,
            actor="other-admin",
            workspace_id="other",
        )

        self.client.post(
            "/documents/upload",
            headers=acme_headers,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        self.client.post(
            "/documents/upload",
            headers=other_headers,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )

        acme_metrics = self.client.get("/metrics/summary", headers=acme_headers)

        self.assertEqual(acme_metrics.status_code, 200)
        self.assertEqual(acme_metrics.json()["documents_total"], 1)

    def test_prediction_json_export_does_not_mark_document_exported(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        export_response = self.client.get("/exports/predictions.json", headers=HEADERS)
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(export_response.status_code, 200)
        self.assertIn("application/json", export_response.headers["content-type"])
        self.assertEqual(
            export_response.headers["content-disposition"],
            'attachment; filename="predictions.json"',
        )
        self.assertEqual(export_response.headers["cache-control"], "no-store")
        data = json.loads(export_response.text)
        self.assertEqual(data[0]["document_id"], document_id)
        self.assertEqual(data[0]["invoice_number"], "INV-001")
        self.assertEqual(data[0]["total"], "110.00")
        self.assertEqual(detail_response.json()["document"]["status"], "needs_review")

    def test_prediction_json_export_skips_documents_without_extraction(self) -> None:
        queued_document_id = self._upload_document()
        processed_document_id = self._upload_document()
        self.client.post(f"/documents/{processed_document_id}/process", headers=HEADERS)

        export_response = self.client.get("/exports/predictions.json", headers=HEADERS)
        queued_detail_response = self.client.get(
            f"/documents/{queued_document_id}", headers=HEADERS
        )

        self.assertEqual(export_response.status_code, 200)
        data = json.loads(export_response.text)
        self.assertEqual([row["document_id"] for row in data], [processed_document_id])
        self.assertEqual(queued_detail_response.json()["document"]["status"], "queued")

    def test_review_queue_and_approve_flow(self) -> None:
        container = self.client.app.state.container
        container.processing_service.extractor.invoice_data = (
            container.processing_service.extractor.invoice_data.__class__(
                vendor_name="Needs Review",
                invoice_number="INV-REVIEW",
                invoice_date=container.processing_service.extractor.invoice_data.invoice_date,
                total=0,
            )
        )
        upload_response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        queue_response = self.client.get("/review/queue", headers=HEADERS)
        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()[0]["id"], document_id)

        worklist_response = self.client.get(
            "/review/worklist?page=1&page_size=10&sort=risk&direction=desc",
            headers=HEADERS,
        )
        self.assertEqual(worklist_response.status_code, 200)
        worklist = worklist_response.json()
        self.assertEqual(worklist["total"], 1)
        self.assertEqual(worklist["summary"]["in_queue"], 1)
        self.assertEqual(worklist["items"][0]["id"], document_id)
        self.assertEqual(worklist["items"][0]["invoice_number"], "INV-REVIEW")
        self.assertIn(worklist["items"][0]["risk"], {"low", "medium", "high"})
        self.assertIn("can_approve", worklist["items"][0])
        self.assertIsNone(worklist["summary"]["average_review_seconds"])

        blank_reject = self.client.post(
            f"/review/{document_id}/reject",
            headers=HEADERS,
            json={"notes": "   "},
        )
        blank_correction = self.client.post(
            f"/documents/{document_id}/request-correction",
            headers=HEADERS,
            json={"reason": "  "},
        )
        self.assertEqual(blank_reject.status_code, 422)
        self.assertEqual(blank_correction.status_code, 422)

        save_response = self.client.post(
            f"/review/{document_id}/save",
            headers=HEADERS,
            json={
                "notes": "fixed",
                "corrected_data": {
                    "vendor_name": "Corrected",
                    "invoice_number": "INV-REVIEW",
                    "invoice_date": "2026-06-18",
                    "total": "25.00",
                    "currency": "USD",
                },
            },
        )
        self.assertEqual(save_response.status_code, 200)

        approve_response = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)
        self.assertEqual(approve_response.status_code, 200)

    def test_exception_worklist_detail_assignment_and_export(self) -> None:
        container = self.client.app.state.container
        current = container.processing_service.extractor.invoice_data
        container.processing_service.extractor.invoice_data = current.__class__(
            vendor_name="Acme Logistics",
            invoice_number=None,
            invoice_date=current.invoice_date,
            due_date=current.due_date,
            subtotal=current.subtotal,
            tax=current.tax,
            total=current.total,
            currency=current.currency,
            line_items=current.line_items,
        )
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.get(
            "/exceptions?scope=blocking&page=1&page_size=10", headers=HEADERS
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["summary"]["open_exceptions"], 1)
        self.assertEqual(payload["summary"]["high_risk"], 1)
        self.assertEqual(payload["summary"]["invoices_affected"], 1)
        self.assertFalse(payload["capabilities"]["resolved_history"])
        exception_id = payload["items"][0]["id"]

        detail = self.client.get(f"/exceptions/{exception_id}", headers=HEADERS)
        assignment = self.client.patch(
            f"/exceptions/{exception_id}/assignment",
            headers=HEADERS,
            json={"assignee": "Senior Reviewer"},
        )
        filtered = self.client.get("/exceptions?owner=Senior%20Reviewer", headers=HEADERS)
        exported = self.client.get("/exceptions/export", headers=HEADERS)

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["exception"]["document_id"], document_id)
        self.assertEqual(assignment.status_code, 200)
        self.assertEqual(assignment.json()["exception"]["owner"], "Senior Reviewer")
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("Missing invoice number", exported.text)

    def test_export_batch_is_eligible_idempotent_and_downloadable(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        approved = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)
        self.assertEqual(approved.status_code, 200)

        workspace = self.client.get("/exports/workspace?view=ready", headers=HEADERS)
        self.assertEqual(workspace.status_code, 200)
        self.assertEqual(workspace.json()["summary"]["ready"]["count"], 1)
        self.assertEqual(workspace.json()["capabilities"]["destinations"][0]["id"], "csv_download")
        self.assertFalse(workspace.json()["capabilities"]["scheduling"])

        created = self.client.post(
            "/exports/batches",
            headers=HEADERS,
            json={"document_ids": [document_id], "mode": "ready"},
        )
        self.assertEqual(created.status_code, 200)
        batch_id = created.json()["batch"]["id"]
        self.assertTrue(
            all(check["state"] == "passed" for check in created.json()["batch"]["eligibility"])
        )

        execution_headers = {**HEADERS, "Idempotency-Key": "export-batch-test-001"}
        first = self.client.post(f"/exports/batches/{batch_id}/execute", headers=execution_headers)
        replay = self.client.post(f"/exports/batches/{batch_id}/execute", headers=execution_headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.json()["run"]["id"], replay.json()["run"]["id"])
        self.assertEqual(first.json()["run"]["status"], "succeeded")

        run_id = first.json()["run"]["id"]
        downloaded = self.client.get(f"/exports/runs/{run_id}/download", headers=HEADERS)
        after = self.client.get("/exports/workspace?view=exported", headers=HEADERS)
        rejected = self.client.post(
            "/exports/batches",
            headers=HEADERS,
            json={"document_ids": [document_id], "mode": "ready"},
        )

        self.assertEqual(downloaded.status_code, 200)
        self.assertIn("text/csv", downloaded.headers["content-type"])
        self.assertIn("document_id,vendor_name", downloaded.text)
        self.assertEqual(after.json()["summary"]["exported"]["count"], 1)
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("already exported", rejected.text)

    def test_export_batch_and_artifact_survive_sqlite_restart(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name) / "export-uploads",
            max_upload_bytes=1000,
            storage_backend="sqlite",
            sqlite_path=Path(self.temp_dir.name) / "export-batches.sqlite3",
        )
        first_client = TestClient(create_app(settings))
        upload = first_client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        first_client.post(f"/documents/{document_id}/process", headers=HEADERS)
        first_client.post(f"/review/{document_id}/approve", headers=HEADERS)
        created = first_client.post(
            "/exports/batches",
            headers=HEADERS,
            json={"document_ids": [document_id], "mode": "ready"},
        )
        batch_id = created.json()["batch"]["id"]
        first_client.app.state.container.documents.store.connection.close()

        second_client = TestClient(create_app(settings))
        restored = second_client.get(
            f"/exports/workspace?view=in_batch&batch_id={batch_id}",
            headers=HEADERS,
        )
        executed = second_client.post(
            f"/exports/batches/{batch_id}/execute",
            headers={**HEADERS, "Idempotency-Key": "persistent-export-001"},
        )
        run_id = executed.json()["run"]["id"]
        second_client.app.state.container.documents.store.connection.close()

        third_client = TestClient(create_app(settings))
        run = third_client.get(f"/exports/runs/{run_id}", headers=HEADERS)
        downloaded = third_client.get(f"/exports/runs/{run_id}/download", headers=HEADERS)
        third_client.app.state.container.documents.store.connection.close()

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["batch"]["id"], batch_id)
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["run"]["status"], "succeeded")
        self.assertEqual(downloaded.status_code, 200)
        self.assertIn("document_id,vendor_name", downloaded.text)

    def test_evaluation_dashboard_reconciles_evidence_and_regression_denominator(self) -> None:
        latest = self.client.get("/evaluation/dashboard", headers=HEADERS)
        comparable = self.client.get(
            "/evaluation/dashboard?run=20260720T042832Z&range_limit=10",
            headers=HEADERS,
        )

        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["selected_run"]["id"], "20260720T043136Z")
        self.assertEqual(latest.json()["selected_run"]["fields_matched"], 79)
        self.assertEqual(latest.json()["selected_run"]["fields_total"], 80)
        self.assertTrue(latest.json()["selected_run"]["passed"])
        self.assertEqual(len(latest.json()["scenario_coverage"]["groups"]), 6)
        self.assertFalse(latest.json()["scenario_coverage"]["included_in_selected_run"])

        self.assertEqual(comparable.status_code, 200)
        regression = comparable.json()["regression"]
        self.assertEqual(regression["comparison_run_id"], "20260720T042050Z")
        self.assertEqual(
            regression["improved"] + regression["stable"] + regression["regressed"],
            regression["comparable_fields"],
        )
        self.assertEqual(regression["comparable_fields"], 8)

    def test_failed_evaluation_attempt_does_not_replace_latest_valid_run(self) -> None:
        class FailingParser:
            provider_name = "failing_parser"

            def parse(self, _source):
                raise ProviderError("provider unavailable", self.provider_name)

        before = self.client.get("/evaluation/dashboard", headers=HEADERS).json()
        self.client.app.state.container.evaluation_dashboard.parser = FailingParser()

        attempted = self.client.post("/evaluation/runs", headers=HEADERS)
        after = self.client.get("/evaluation/dashboard", headers=HEADERS).json()

        self.assertEqual(attempted.status_code, 502)
        self.assertEqual(
            after["selected_run"]["id"],
            before["selected_run"]["id"],
        )
        self.assertEqual(after["attempts"][0]["status"], "failed")
        self.assertEqual(after["attempts"][0]["documents_processed"], 0)

    def test_completed_evaluation_is_stored_as_a_valid_run(self) -> None:
        completed = self.client.post("/evaluation/runs", headers=HEADERS)

        self.assertEqual(completed.status_code, 200)
        run_id = completed.json()["run_id"]
        dashboard = self.client.get(
            f"/evaluation/dashboard?run={run_id}",
            headers=HEADERS,
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["selected_run"]["id"], run_id)
        self.assertEqual(dashboard.json()["selected_run"]["source"], "workspace_history")
        self.assertEqual(dashboard.json()["attempts"][0]["status"], "succeeded")
        self.assertEqual(dashboard.json()["attempts"][0]["run_id"], run_id)

    def test_process_unknown_document_is_not_found(self) -> None:
        response = self.client.post(f"/documents/{uuid4()}/process", headers=HEADERS)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found")

    def test_process_same_document_twice_is_conflict(self) -> None:
        document_id = self._upload_document()

        first_response = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        second_response = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)

    def test_sqlite_process_response_returns_final_job_state(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name) / "sqlite-uploads",
            max_upload_bytes=1000,
            storage_backend="sqlite",
            sqlite_path=Path(self.temp_dir.name) / "doc_intel.sqlite3",
        )
        sqlite_client = TestClient(create_app(settings))
        try:
            upload_response = sqlite_client.post(
                "/documents/upload",
                headers=HEADERS,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            document_id = upload_response.json()["document"]["id"]

            process_response = sqlite_client.post(
                f"/documents/{document_id}/process", headers=HEADERS
            )
        finally:
            sqlite_client.app.state.container.documents.store.connection.close()

        self.assertEqual(process_response.status_code, 200)
        self.assertEqual(process_response.json()["document"]["status"], "needs_review")
        self.assertEqual(process_response.json()["job"]["status"], "succeeded")
        self.assertEqual(process_response.json()["job"]["provider_name"], "mock_extractor")

    def test_provider_failure_returns_safe_failed_response(self) -> None:
        container = self.client.app.state.container
        container.processing_service.parser = MockParserProvider(text="")
        document_id = self._upload_document()

        response = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["status"], "failed")
        self.assertEqual(response.json()["job"]["error_message"], "provider_error:mock_parser")

    def test_review_unknown_document_is_not_found(self) -> None:
        document_id = uuid4()

        responses = (
            self.client.post(f"/review/{document_id}/save", headers=HEADERS, json={"notes": ""}),
            self.client.post(f"/review/{document_id}/approve", headers=HEADERS),
            self.client.post(
                f"/review/{document_id}/reject",
                headers=HEADERS,
                json={"notes": "Invoice is not valid."},
            ),
        )

        for response in responses:
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "Not found")

    def test_reapproving_approved_document_is_conflict(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        first_response = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        response = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(response.status_code, 409)

    def test_response_does_not_expose_internal_identifiers(self) -> None:
        document_id = self._upload_document()
        process_response = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        response_text = f"{process_response.text}\n{detail_response.text}"

        self.assertNotIn("storage_key", response_text)
        self.assertNotIn("provider_trace_id", response_text)
        self.assertNotIn("APP_ADMIN_TOKEN", response_text)
        self.assertNotIn(TOKEN, response_text)
        self.assertNotIn(str(Path(self.temp_dir.name)), response_text)

    def test_production_rejects_weak_token_and_disables_docs(self) -> None:
        weak_settings = Settings(
            app_env="production",
            admin_token="test-token",
            metrics_token="metrics-token-with-24-characters",
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        with self.assertRaises(ValueError):
            create_app(weak_settings)

        strong_settings = Settings(
            app_env="production",
            admin_token="x" * 24,
            metrics_token="metrics-token-with-24-characters",
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
            malware_scanner_backend="clamav",
        )
        production_client = TestClient(create_app(strong_settings))

        self.assertEqual(production_client.get("/docs").status_code, 404)
        self.assertEqual(production_client.get("/openapi.json").status_code, 404)

    def test_public_demo_rejects_real_providers(self) -> None:
        settings = Settings(
            app_env="public-demo",
            admin_token="admin-token-with-24-characters",
            metrics_token="metrics-token-with-24-characters",
            uploader_token="upload-token-with-24-characters",
            reviewer_token="review-token-with-24-characters",
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
            parser_provider="mistral_ocr",
            extractor_provider="mock",
        )

        with self.assertRaises(ValueError):
            create_app(settings)

    def _upload_document(self) -> str:
        response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["document"]["id"]


if __name__ == "__main__":
    unittest.main()
