from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class AgentCopilotApiTests(unittest.TestCase):
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

    def test_copilot_summarizes_workflow_state_and_records_run(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "Summarize workflow metrics and cost"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "get_metrics_summary")
        self.assertEqual(payload["response"]["status"], "success")
        self.assertEqual(payload["response"]["data"]["documents_total"], 1)
        self.assertEqual(payload["run"]["selected_tool"], "get_metrics_summary")
        self.assertEqual(payload["run"]["tool_calls"][0]["risk"], "read_only")
        self.assertEqual(len(self.client.app.state.container.agent_runs.records), 1)

    def test_copilot_explains_document_detail_without_mutation(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "Explain this invoice", "document_id": document_id},
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "get_document_detail")
        self.assertEqual(payload["response"]["data"]["document"]["id"], document_id)
        self.assertEqual(payload["response"]["data"]["document"]["status"], "approved")
        self.assertEqual(
            payload["response"]["data"]["extraction"]["data"]["invoice_number"], "INV-001"
        )
        recommendation = payload["response"]["data"]["recommendation"]
        self.assertEqual(recommendation["recommended_tool"], "export_approved_csv")
        self.assertEqual(recommendation["risk"], "admin_action")
        self.assertTrue(recommendation["requires_confirmation"])
        self.assertEqual(detail_response.json()["document"]["status"], "approved")

    def test_copilot_recommends_processing_for_unprocessed_document(self) -> None:
        document_id = self._upload_document()

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "What should I do with this invoice?", "document_id": document_id},
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        recommendation = payload["response"]["data"]["recommendation"]
        self.assertEqual(recommendation["recommended_tool"], "process_document")
        self.assertEqual(recommendation["risk"], "operator_action")
        self.assertTrue(recommendation["requires_confirmation"])
        self.assertIn("Do not approve before extraction", recommendation["why_not"][0])
        self.assertEqual(detail_response.json()["document"]["status"], "queued")

    def test_copilot_recommends_human_review_for_needs_review_document(self) -> None:
        container = self.client.app.state.container
        container.processing_service.extractor.invoice_data = (
            container.processing_service.extractor.invoice_data.__class__(
                vendor_name="Needs Review",
                invoice_number="INV-REVIEW",
                invoice_date=container.processing_service.extractor.invoice_data.invoice_date,
                total=0,
            )
        )
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "Recommend next step", "document_id": document_id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        recommendation = payload["response"]["data"]["recommendation"]
        self.assertEqual(recommendation["recommended_tool"], "save_review_notes")
        self.assertEqual(recommendation["risk"], "review_action")
        self.assertTrue(recommendation["requires_human"])
        self.assertIn("validation_issues=", recommendation["evidence"][-1])

    def test_copilot_recommends_review_queue_from_metrics(self) -> None:
        container = self.client.app.state.container
        container.processing_service.extractor.invoice_data = (
            container.processing_service.extractor.invoice_data.__class__(
                vendor_name="Needs Review",
                invoice_number="INV-REVIEW",
                invoice_date=container.processing_service.extractor.invoice_data.invoice_date,
                total=0,
            )
        )
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "Summarize workflow metrics"},
        )

        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["response"]["data"]["recommendation"]
        self.assertEqual(recommendation["recommended_tool"], "list_review_queue")
        self.assertEqual(recommendation["risk"], "read_only")
        self.assertTrue(recommendation["requires_human"])

    def test_copilot_blocks_direct_execution_request_in_step5(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={"message": "Approve and export this document", "document_id": document_id},
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "get_document_detail")
        self.assertIn("blocked direct execution", payload["run"]["blocked_actions"][0])
        self.assertEqual(payload["run"]["tool_calls"][0]["risk"], "read_only")
        self.assertEqual(
            payload["response"]["data"]["recommendation"]["recommended_tool"],
            "export_approved_csv",
        )
        self.assertEqual(detail_response.json()["document"]["status"], "approved")

    def test_operator_gets_human_escalation_for_admin_only_recommendation(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        operator_headers = {**HEADERS, "X-Role": "operator", "X-User-Id": "operator-1"}

        response = self.client.post(
            "/agent/copilot",
            headers=operator_headers,
            json={"message": "What next?", "document_id": document_id},
        )

        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["response"]["data"]["recommendation"]
        self.assertEqual(recommendation["recommended_tool"], None)
        self.assertEqual(recommendation["risk"], "blocked")
        self.assertTrue(recommendation["requires_human"])
        self.assertIn("current role cannot use export_approved_csv", recommendation["why"])

    def test_controlled_process_requires_confirmation_without_mutation(self) -> None:
        document_id = self._upload_document()

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Run processing for this document",
                "document_id": document_id,
                "execute_tool": "process_document",
            },
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["status"], "confirmation_required")
        self.assertEqual(payload["response"]["failure_type"], "confirmation_required")
        self.assertEqual(payload["run"]["selected_tool"], "process_document")
        self.assertEqual(detail_response.json()["document"]["status"], "queued")

    def test_confirmed_controlled_process_executes_through_project2_workflow(self) -> None:
        document_id = self._upload_document()

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Run processing for this document",
                "document_id": document_id,
                "execute_tool": "process_document",
                "confirmed": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "process_document")
        self.assertEqual(payload["response"]["status"], "success")
        self.assertEqual(payload["response"]["risk"], "operator_action")
        self.assertEqual(payload["response"]["data"]["document"]["status"], "approved")
        self.assertEqual(payload["response"]["data"]["job"]["status"], "succeeded")
        self.assertEqual(payload["run"]["intent"], "execute_controlled_tool")
        self.assertEqual(payload["run"]["tool_calls"][0]["status"], "success")

    def test_controlled_process_invalid_state_is_traced_not_executed_again(self) -> None:
        document_id = self._upload_document()
        self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Run processing for this document",
                "document_id": document_id,
                "execute_tool": "process_document",
                "confirmed": True,
            },
        )

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Run processing again",
                "document_id": document_id,
                "execute_tool": "process_document",
                "confirmed": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["status"], "failed")
        self.assertEqual(payload["response"]["failure_type"], "invalid_workflow_state")
        self.assertIn("Cannot process job", payload["response"]["summary"])

    def test_confirmed_export_executes_and_marks_approved_documents_exported(self) -> None:
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        response = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Export approved invoices",
                "execute_tool": "export_approved_csv",
                "confirmed": True,
            },
        )
        detail_response = self.client.get(f"/documents/{document_id}", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "export_approved_csv")
        self.assertEqual(payload["response"]["status"], "success")
        self.assertEqual(payload["response"]["data"]["exported_rows"], 1)
        self.assertIn(document_id, payload["response"]["data"]["csv_text"])
        self.assertEqual(detail_response.json()["document"]["status"], "exported")

    def test_controlled_execution_does_not_cross_workspace_boundary(self) -> None:
        acme_headers = {**HEADERS, "X-Workspace-Id": "acme", "X-User-Id": "acme-admin"}
        other_headers = {**HEADERS, "X-Workspace-Id": "other", "X-User-Id": "other-admin"}
        document_id = self._upload_document(headers=acme_headers)

        response = self.client.post(
            "/agent/copilot",
            headers=other_headers,
            json={
                "message": "Run processing for this document",
                "document_id": document_id,
                "execute_tool": "process_document",
                "confirmed": True,
            },
        )
        acme_detail_response = self.client.get(f"/documents/{document_id}", headers=acme_headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["status"], "escalated")
        self.assertEqual(payload["response"]["failure_type"], "workspace_boundary_violation")
        self.assertNotIn("document", payload["response"]["data"])
        self.assertEqual(acme_detail_response.json()["document"]["status"], "queued")

    def test_copilot_does_not_leak_cross_tenant_document_detail(self) -> None:
        acme_headers = {**HEADERS, "X-Workspace-Id": "acme", "X-User-Id": "acme-admin"}
        other_headers = {**HEADERS, "X-Workspace-Id": "other", "X-User-Id": "other-admin"}
        document_id = self._upload_document(headers=acme_headers)

        response = self.client.post(
            "/agent/copilot",
            headers=other_headers,
            json={"message": "Explain this document", "document_id": document_id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run"]["workspace_id"], "other")
        self.assertEqual(payload["response"]["tool_name"], "get_document_detail")
        self.assertEqual(payload["response"]["status"], "escalated")
        self.assertEqual(payload["response"]["failure_type"], "workspace_boundary_violation")
        self.assertNotIn("document", payload["response"]["data"])
        self.assertEqual(
            payload["response"]["data"]["recommendation"]["action"],
            "Escalate to human reviewer",
        )
        self.assertNotIn(document_id, payload["response"]["summary"])

    def test_reviewer_can_ask_for_review_queue(self) -> None:
        container = self.client.app.state.container
        container.processing_service.extractor.invoice_data = (
            container.processing_service.extractor.invoice_data.__class__(
                vendor_name="Needs Review",
                invoice_number="INV-REVIEW",
                invoice_date=container.processing_service.extractor.invoice_data.invoice_date,
                total=0,
            )
        )
        document_id = self._upload_document()
        self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        reviewer_headers = {**HEADERS, "X-Role": "reviewer", "X-User-Id": "reviewer-1"}

        response = self.client.post(
            "/agent/copilot",
            headers=reviewer_headers,
            json={"message": "What is in the human review queue?"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"]["tool_name"], "list_review_queue")
        self.assertEqual(payload["response"]["data"]["documents"][0]["id"], document_id)
        self.assertEqual(payload["run"]["actor"], "reviewer-1")

    def _upload_document(self, headers: dict[str, str] | None = None) -> str:
        response = self.client.post(
            "/documents/upload",
            headers=headers or HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["document"]["id"]


if __name__ == "__main__":
    unittest.main()
