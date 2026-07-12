from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.extraction.schemas import SCHEMA_VERSION
from app.main import create_app
from app.providers.mock import MockParserProvider


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

    def test_ui_requires_login_and_sets_cookie(self) -> None:
        login_page = self.client.get("/ui")

        self.assertEqual(login_page.status_code, 200)
        self.assertIn("Sign in to the console", login_page.text)

        response = self.client.post(
            "/ui/login",
            data={"admin_token": TOKEN},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("doc_intel_admin_token", response.headers["set-cookie"])

    def test_ui_upload_process_and_export_flow(self) -> None:
        self._ui_login()
        upload_response = self.client.post(
            "/ui/documents/upload",
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            follow_redirects=False,
        )
        self.assertEqual(upload_response.status_code, 303)
        document_id = upload_response.headers["location"].split("document_id=")[1].split("&")[0]

        process_response = self.client.post(
            f"/ui/documents/{document_id}/process",
            follow_redirects=False,
        )
        self.assertEqual(process_response.status_code, 303)

        dashboard_response = self.client.get(f"/ui?document_id={document_id}")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("Acme Logistics", dashboard_response.text)
        self.assertIn("needs_review", dashboard_response.text)
        self.assertIn("Approve", dashboard_response.text)
        self.assertIn(f"/ui/documents/{document_id}/preview", dashboard_response.text)
        self.assertIn("Ask Copilot", dashboard_response.text)
        self.assertIn("Summarize workflow", dashboard_response.text)

        approve_response = self.client.post(
            f"/ui/review/{document_id}/approve",
            follow_redirects=False,
        )
        self.assertEqual(approve_response.status_code, 303)

        export_response = self.client.get("/ui/export")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("text/csv", export_response.headers["content-type"])
        self.assertIn(document_id, export_response.text)

    def test_ui_export_uses_no_store_headers(self) -> None:
        self._ui_login()
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        response = self.client.get("/ui/export")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(response.headers["expires"], "0")

    def test_ui_pdf_preview_requires_login_and_streams_inline_pdf(self) -> None:
        self._ui_login()
        upload_response = self.client.post(
            "/ui/documents/upload",
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            follow_redirects=False,
        )
        document_id = upload_response.headers["location"].split("document_id=")[1].split("&")[0]

        anonymous_client = TestClient(create_app(self.client.app.state.container.settings))
        unauthorized_response = anonymous_client.get(f"/ui/documents/{document_id}/preview")
        preview_response = self.client.get(f"/ui/documents/{document_id}/preview")

        self.assertEqual(unauthorized_response.status_code, 401)
        self.assertEqual(preview_response.status_code, 200)
        self.assertIn("application/pdf", preview_response.headers["content-type"])
        self.assertIn("inline", preview_response.headers["content-disposition"])
        self.assertEqual(preview_response.headers["cache-control"], "no-store")
        self.assertEqual(preview_response.headers["pragma"], "no-cache")
        self.assertEqual(preview_response.headers["expires"], "0")
        self.assertTrue(preview_response.content.startswith(b"%PDF-"))

    def test_ui_copilot_panel_summarizes_workflow(self) -> None:
        self._ui_login()

        response = self.client.post(
            "/ui/copilot",
            data={"action": "summarize"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ask Copilot", response.text)
        self.assertIn("get_metrics_summary", response.text)
        self.assertIn("Confidence:", response.text)
        self.assertIn("Recommendation", response.text)

    def test_ui_copilot_executes_selected_document_with_confirmation(self) -> None:
        self._ui_login()
        document_id = self._upload_document()

        response = self.client.post(
            "/ui/copilot",
            data={
                "action": "execute",
                "document_id": document_id,
                "execute_tool": "process_document",
            },
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertIn("process_document", response.text)
        self.assertIn("status is now needs_review", response.text)
        self.assertEqual(detail_response.json()["document"]["status"], "needs_review")

    def test_ui_agentops_dashboard_empty_state_requires_login(self) -> None:
        login_response = self.client.get("/ui/agentops")

        self.assertEqual(login_response.status_code, 200)
        self.assertIn("Sign in to the console", login_response.text)

        self._ui_login()
        response = self.client.get("/ui/agentops")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Copilot evaluation dashboard", response.text)
        self.assertIn("No copilot runs yet", response.text)
        self.assertIn("Tool accuracy", response.text)
        self.assertIn("Prompt comparison", response.text)

    def test_ui_agentops_dashboard_updates_from_copilot_runs(self) -> None:
        self._ui_login()
        self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Summarize workflow metrics and cost",
                "expected_tool": "get_metrics_summary",
            },
        )

        response = self.client.get("/ui/agentops")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Run timeline", response.text)
        self.assertIn("summarize_workflow", response.text)
        self.assertIn("get_metrics_summary", response.text)
        self.assertIn("deterministic-v1", response.text)
        self.assertIn("Failure trend", response.text)
        self.assertIn("Regression window", response.text)

    def test_ui_backoffice_dashboard_empty_state_requires_login(self) -> None:
        login_response = self.client.get("/ui/backoffice")

        self.assertEqual(login_response.status_code, 200)
        self.assertIn("Sign in to the console", login_response.text)

        self._ui_login()
        response = self.client.get("/ui/backoffice")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Operator inbox", response.text)
        self.assertIn("Create work item", response.text)
        self.assertIn("No work item selected", response.text)

    def test_ui_backoffice_create_plan_approve_and_execute_export(self) -> None:
        self._ui_login()
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        create_response = self.client.post(
            "/ui/backoffice/work-items",
            data={
                "title": "Export approved invoice",
                "work_type": "invoice_export",
                "document_id": document_id,
                "requested_outcome": "export invoice",
            },
            follow_redirects=False,
        )
        self.assertEqual(create_response.status_code, 303)
        work_item_id = create_response.headers["location"].split("work_item_id=")[1].split("&")[0]

        plan_response = self.client.post(
            f"/ui/backoffice/work-items/{work_item_id}/plan",
            data={
                "requested_outcome": "export invoice",
                "evidence_sufficient": "true",
                "approved_for_export": "true",
                "missing_fields": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(plan_response.status_code, 303)

        container = self.client.app.state.container
        work_item = container.backoffice_work_items.get(UUID(work_item_id))
        plan = container.backoffice_plans.get(work_item.current_plan_id)
        approval = container.backoffice_approvals.list_pending("default")[0]
        export_step = next(
            step for step in plan.steps if step.action_type.value == "export_approved_invoice"
        )
        page_before_approval = self.client.get(f"/ui/backoffice?work_item_id={work_item_id}")

        self.assertIn("Export preview", page_before_approval.text)
        self.assertIn("Approve", page_before_approval.text)
        self.assertNotIn(">Execute<", page_before_approval.text)

        approve_response = self.client.post(
            f"/ui/backoffice/approvals/{approval.id}/approve",
            data={
                "work_item_id": work_item_id,
                "notes": "Approved for export.",
            },
            follow_redirects=False,
        )
        self.assertEqual(approve_response.status_code, 303)
        page_after_approval = self.client.get(f"/ui/backoffice?work_item_id={work_item_id}")
        self.assertIn(">Execute<", page_after_approval.text)

        execute_response = self.client.post(
            f"/ui/backoffice/work-items/{work_item_id}/steps/{export_step.id}/execute",
            follow_redirects=False,
        )
        document_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(execute_response.status_code, 303)
        self.assertEqual(document_response.json()["document"]["status"], "exported")

    def test_ui_pdf_preview_unknown_document_is_not_found(self) -> None:
        self._ui_login()

        response = self.client.get(f"/ui/documents/{uuid4()}/preview")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Not found")

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
        reviewer_headers = {**HEADERS, "X-Role": "reviewer", "X-User-Id": "reviewer-1"}

        queue_response = self.client.get("/review/queue", headers=reviewer_headers)
        approve_response = self.client.post(
            f"/review/{document_id}/approve",
            headers=reviewer_headers,
        )

        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()[0]["id"], document_id)
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["review_task"]["status"], "approved")

    def test_operator_role_cannot_use_review_api(self) -> None:
        upload_response = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload_response.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        operator_headers = {**HEADERS, "X-Role": "operator", "X-User-Id": "operator-1"}

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
            headers=HEADERS,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["status"], "exported")
        self.assertEqual(response.json()["integration"]["adapter_name"], "mock-accounting")
        self.assertEqual(response.json()["integration"]["external_id"], "mock-ap-INV-001")

    def test_api_document_access_is_scoped_by_workspace(self) -> None:
        acme_headers = {
            **HEADERS,
            "X-Workspace-Id": "acme",
            "X-User-Id": "acme-admin",
            "X-Role": "admin",
        }
        other_headers = {
            **HEADERS,
            "X-Workspace-Id": "other",
            "X-User-Id": "other-admin",
            "X-Role": "admin",
        }

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
        acme_headers = {**HEADERS, "X-Workspace-Id": "acme"}
        other_headers = {**HEADERS, "X-Workspace-Id": "other"}

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
            self.client.post(f"/review/{document_id}/reject", headers=HEADERS, json={"notes": ""}),
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
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        with self.assertRaises(ValueError):
            create_app(weak_settings)

        strong_settings = Settings(
            app_env="production",
            admin_token="x" * 24,
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        production_client = TestClient(create_app(strong_settings))

        self.assertEqual(production_client.get("/docs").status_code, 404)
        self.assertEqual(production_client.get("/openapi.json").status_code, 404)

    def test_production_ui_cookie_is_secure(self) -> None:
        settings = Settings(
            app_env="production",
            admin_token="x" * 24,
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        client = TestClient(create_app(settings))

        response = client.post(
            "/ui/login",
            data={"admin_token": "x" * 24},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("secure", response.headers["set-cookie"].lower())
        self.assertIn("httponly", response.headers["set-cookie"].lower())

    def test_public_demo_rejects_real_providers(self) -> None:
        settings = Settings(
            app_env="public-demo",
            admin_token=TOKEN,
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

    def _ui_login(self) -> None:
        response = self.client.post("/ui/login", data={"admin_token": TOKEN})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
