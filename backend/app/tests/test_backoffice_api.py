from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.extraction.schemas import SCHEMA_VERSION
from app.main import create_app


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class BackofficeApiTests(unittest.TestCase):
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

    def test_workspace_requires_admin_token(self) -> None:
        response = self.client.get("/backoffice/workspace")

        self.assertEqual(response.status_code, 401)

    def test_workspace_lists_work_items_documents_and_metrics(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
        self.assertEqual(upload.status_code, 200)

        response = self.client.get("/backoffice/workspace", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workspace_id"], "default")
        self.assertEqual(payload["work_items"], [])
        self.assertEqual(payload["pending_approvals"], [])
        self.assertEqual(len(payload["documents"]), 1)
        self.assertEqual(payload["documents"][0]["document_type"], "invoice")
        self.assertEqual(
            payload["documents"][0]["supported_extraction_schema"],
            SCHEMA_VERSION,
        )
        self.assertIn("metrics", payload)

    def test_create_plan_approve_and_execute_export_via_json_api(self) -> None:
        document_id = self._approved_document_id()
        created = self.client.post(
            "/backoffice/work-items",
            headers=HEADERS,
            json={
                "title": "Export approved invoice",
                "work_type": "invoice_export",
                "linked_document_ids": [document_id],
                "requested_outcome": "export invoice",
            },
        )
        self.assertEqual(created.status_code, 201)
        work_item_id = created.json()["work_item"]["id"]

        planned = self.client.post(
            f"/backoffice/work-items/{work_item_id}/plan",
            headers=HEADERS,
            json={
                "requested_outcome": "export invoice",
                "evidence_sufficient": True,
                "approved_for_export": True,
                "missing_fields": [],
            },
        )
        self.assertEqual(planned.status_code, 200)
        planned_item = planned.json()["work_item"]
        self.assertEqual(
            [step["action_type"] for step in planned_item["current_plan"]["steps"]],
            ["inspect_queue", "export_approved_invoice"],
        )
        approval = planned_item["approvals"][0]
        export_step = planned_item["current_plan"]["steps"][1]
        self.assertEqual(approval["status"], "pending")

        approved = self.client.post(
            f"/backoffice/approvals/{approval['id']}/approve",
            headers=HEADERS,
            json={"notes": "Approved for demo"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["approval"]["status"], "approved")

        executed = self.client.post(
            f"/backoffice/work-items/{work_item_id}/steps/{export_step['id']}/execute",
            headers=HEADERS,
        )
        self.assertEqual(executed.status_code, 200)
        self.assertEqual(executed.json()["tool_response"]["status"], "success")
        self.assertEqual(executed.json()["work_item"]["status"], "resolved")

    def test_work_item_detail_is_workspace_scoped(self) -> None:
        created = self.client.post(
            "/backoffice/work-items",
            headers=HEADERS,
            json={"title": "Review invoice", "work_type": "invoice_review"},
        )
        work_item_id = created.json()["work_item"]["id"]

        response = self.client.get(
            f"/backoffice/work-items/{work_item_id}",
            headers={**HEADERS, "X-Workspace-Id": "other"},
        )

        self.assertEqual(response.status_code, 404)

    def test_plan_ignores_client_claim_that_unprocessed_document_is_approved(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        created = self.client.post(
            "/backoffice/work-items",
            headers=HEADERS,
            json={
                "title": "Unsafe export request",
                "work_type": "invoice_export",
                "linked_document_ids": [document_id],
                "requested_outcome": "export invoice",
            },
        )
        work_item_id = created.json()["work_item"]["id"]

        planned = self.client.post(
            f"/backoffice/work-items/{work_item_id}/plan",
            headers=HEADERS,
            json={
                "requested_outcome": "export invoice",
                "evidence_sufficient": True,
                "approved_for_export": True,
                "missing_fields": [],
            },
        )

        item = planned.json()["work_item"]
        self.assertEqual(item["current_plan"]["overall_confidence"], "low")
        self.assertIn("Insufficient evidence", item["current_plan"]["escalation_reason"])
        self.assertEqual(item["approvals"], [])

    def test_update_work_item_persists_operational_metadata_and_activity(self) -> None:
        created = self.client.post(
            "/backoffice/work-items",
            headers=HEADERS,
            json={"title": "Review invoice", "work_type": "invoice_review"},
        )
        work_item_id = created.json()["work_item"]["id"]

        updated = self.client.patch(
            f"/backoffice/work-items/{work_item_id}",
            headers=HEADERS,
            json={
                "title": "Review priority invoice",
                "priority": "urgent",
                "assignee": "Senior Reviewer",
                "requested_outcome": "Approve or request correction",
                "tags": ["invoice", "priority", "invoice"],
            },
        )

        self.assertEqual(updated.status_code, 200)
        item = updated.json()["work_item"]
        self.assertEqual(item["title"], "Review priority invoice")
        self.assertEqual(item["priority"], "urgent")
        self.assertEqual(item["assignee"], "Senior Reviewer")
        self.assertEqual(item["tags"], ["invoice", "priority"])
        self.assertIn("work_item_updated", [event["event_type"] for event in item["activity"]])

    def test_draft_edit_and_regenerate_create_reviewable_version_history(self) -> None:
        document_id = self._approved_document_id()
        created = self.client.post(
            "/backoffice/work-items",
            headers=HEADERS,
            json={
                "title": "Prepare accounting note",
                "work_type": "accounting_note",
                "linked_document_ids": [document_id],
            },
        )
        work_item_id = created.json()["work_item"]["id"]
        planned = self.client.post(
            f"/backoffice/work-items/{work_item_id}/plan",
            headers=HEADERS,
            json={"requested_outcome": "Prepare accounting note"},
        ).json()["work_item"]
        draft_id = planned["drafts"][0]["id"]

        edited = self.client.patch(
            f"/backoffice/work-items/{work_item_id}/drafts/{draft_id}",
            headers=HEADERS,
            json={"preview_content": "Reviewed accounting note."},
        )
        regenerated = self.client.post(
            f"/backoffice/work-items/{work_item_id}/drafts/{draft_id}/regenerate",
            headers=HEADERS,
        )
        detail = self.client.get(f"/backoffice/work-items/{work_item_id}", headers=HEADERS).json()[
            "work_item"
        ]

        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["draft"]["preview_content"], "Reviewed accounting note.")
        self.assertEqual(regenerated.status_code, 200)
        self.assertEqual(len(detail["drafts"]), 2)
        self.assertIn("draft_regenerated", [event["event_type"] for event in detail["activity"]])

    def _approved_document_id(self) -> str:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
        self.assertEqual(upload.status_code, 200)
        document_id = upload.json()["document"]["id"]
        process = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.assertEqual(process.status_code, 200)
        approval = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)
        self.assertEqual(approval.status_code, 200)
        detail = self.client.get(f"/documents/{document_id}", headers=HEADERS)
        self.assertEqual(detail.json()["document"]["status"], "approved")
        return str(UUID(document_id))


if __name__ == "__main__":
    unittest.main()
