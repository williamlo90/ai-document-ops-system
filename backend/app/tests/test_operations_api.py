from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.backoffice.models import WorkType
from app.backoffice.planner import PlanningInput
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.main import create_app


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class OperationsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = TestClient(
            create_app(
                Settings(
                    app_env="test",
                    admin_token=TOKEN,
                    upload_root=Path(self.temp_dir.name),
                    max_upload_bytes=1000,
                )
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_notification_projection_unread_mark_read_and_deep_link(self) -> None:
        service = self.client.app.state.container.backoffice_service
        item = service.create_work_item(
            title="Approved invoice export",
            context=_context(),
            work_type=WorkType.INVOICE_EXPORT,
            linked_document_ids=(uuid4(),),
        )
        service.plan_work_item(
            work_item_id=item.id,
            context=_context(),
            planning_input=PlanningInput(
                requested_outcome="export",
                approved_for_export=True,
            ),
        )

        feed = self.client.get("/operations/notifications", headers=HEADERS).json()
        notification = next(
            item
            for item in feed["notifications"]
            if item["notification_type"] == "approval_requested"
        )
        self.assertGreater(feed["unread_count"], 0)
        self.assertEqual(notification["work_item_id"], str(item.id))

        marked = self.client.post(
            f"/operations/notifications/{notification['id']}/read", headers=HEADERS
        )
        refreshed = self.client.get("/operations/notifications", headers=HEADERS).json()
        self.assertEqual(marked.status_code, 200)
        self.assertIsNotNone(
            next(item for item in refreshed["notifications"] if item["id"] == notification["id"])[
                "read_at"
            ]
        )

    def test_worker_health_and_audit_export_are_admin_operations(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- test", "application/pdf")},
        )
        self.assertEqual(upload.status_code, 200)

        worker = self.client.get("/operations/jobs", headers=HEADERS)
        audit = self.client.get("/operations/audit.csv", headers=HEADERS)

        self.assertEqual(worker.status_code, 200)
        self.assertEqual(worker.json()["worker"]["status"], "healthy")
        self.assertIn("text/csv", audit.headers["content-type"])
        self.assertIn("document_uploaded", audit.text)

    def test_operations_require_admin_token(self) -> None:
        self.assertEqual(self.client.get("/operations/notifications").status_code, 401)
        self.assertEqual(self.client.get("/operations/jobs").status_code, 401)
        self.assertEqual(self.client.get("/operations/audit.csv").status_code, 401)


def _context() -> SecurityContext:
    return SecurityContext(
        actor="admin",
        workspace_id="default",
        role="admin",
        is_admin=True,
    )


if __name__ == "__main__":
    unittest.main()
