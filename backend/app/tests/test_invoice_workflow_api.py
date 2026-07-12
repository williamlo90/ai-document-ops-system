from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.documents.status import DocumentStatus
from app.main import create_app


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class InvoiceWorkflowApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        self.app = create_app(settings)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_workflow_aggregate_merges_document_and_backoffice_activity(self) -> None:
        document_id, work_item_id = self._approved_invoice_with_plan()

        response = self.client.get(f"/invoices/{document_id}/workflow", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        workflow = response.json()
        self.assertEqual(workflow["document"]["status"], "approved")
        self.assertEqual(workflow["work_item"]["id"], work_item_id)
        self.assertEqual(workflow["current_stage"], "planning")
        self.assertEqual(workflow["current_owner"], "AI Workflow")
        event_types = [event["event_type"] for event in workflow["activity"]]
        self.assertIn("document_uploaded", event_types)
        self.assertIn("processing_finished", event_types)
        self.assertIn("work_item_created", event_types)
        self.assertIn("plan_generated", event_types)
        timestamps = [event["created_at"] for event in workflow["activity"]]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_correction_and_escalation_are_durable_workflow_actions(self) -> None:
        document_id, _work_item_id = self._approved_invoice_with_plan()

        correction = self.client.post(
            f"/invoices/{document_id}/request-correction",
            headers=HEADERS,
            json={"reason": "Confirm the purchase order reference."},
        )
        escalation = self.client.post(
            f"/invoices/{document_id}/escalate",
            headers=HEADERS,
            json={"reason": "Senior reviewer decision required."},
        )
        workflow = self.client.get(f"/invoices/{document_id}/workflow", headers=HEADERS).json()

        self.assertEqual(correction.status_code, 200)
        self.assertEqual(escalation.status_code, 200)
        self.assertEqual(workflow["current_stage"], "needs_attention")
        event_types = [event["event_type"] for event in workflow["activity"]]
        self.assertIn("correction_requested", event_types)
        self.assertIn("workflow_escalated", event_types)

    def test_failed_document_can_be_queued_for_one_manual_retry(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        document = self.app.state.container.documents.get(UUID(document_id))
        document.status = DocumentStatus.FAILED
        document.error_message = "provider_error:test"
        self.app.state.container.documents.add(document)

        retry = self.client.post(f"/invoices/{document_id}/retry", headers=HEADERS)
        duplicate = self.client.post(f"/invoices/{document_id}/retry", headers=HEADERS)
        workflow = self.client.get(f"/invoices/{document_id}/workflow", headers=HEADERS).json()

        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["document"]["status"], "queued")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(workflow["current_stage"], "extracting")
        self.assertIn(
            "manual retry requested",
            [event["summary"] for event in workflow["activity"]],
        )

    def test_workflow_is_workspace_scoped(self) -> None:
        document_id, _work_item_id = self._approved_invoice_with_plan()

        response = self.client.get(
            f"/invoices/{document_id}/workflow",
            headers={**HEADERS, "X-Workspace-Id": "other"},
        )

        self.assertEqual(response.status_code, 404)

    def _approved_invoice_with_plan(self) -> tuple[str, str]:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        process = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.assertEqual(process.json()["document"]["status"], "approved")
        created = self.client.post(
            "/backoffice/work-items",
            headers={**HEADERS, "Idempotency-Key": f"create:{document_id}"},
            json={
                "title": "Review approved invoice",
                "work_type": "invoice_review",
                "linked_document_ids": [document_id],
                "requested_outcome": "review invoice",
            },
        )
        work_item_id = created.json()["work_item"]["id"]
        planned = self.client.post(
            f"/backoffice/work-items/{work_item_id}/plan",
            headers={**HEADERS, "Idempotency-Key": f"plan:{document_id}"},
            json={"requested_outcome": "review invoice"},
        )
        self.assertEqual(planned.status_code, 200)
        return document_id, work_item_id


if __name__ == "__main__":
    unittest.main()
