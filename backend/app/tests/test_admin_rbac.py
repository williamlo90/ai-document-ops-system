from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.tests.auth_helpers import session_headers


class AdminRbacTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token="admin-test-token",
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1_000,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def test_uploader_and_reviewer_are_denied_admin_surfaces(self) -> None:
        admin_only_requests = (
            ("GET", "/system/dashboard", None),
            ("GET", "/operations/notifications", None),
            ("GET", "/operations/jobs", None),
            ("GET", "/operations/audit.csv", None),
            ("GET", "/providers/health", None),
            ("GET", "/integrations/status", None),
            ("POST", "/integrations/email/test", None),
            ("GET", "/agentops/summary", None),
            ("GET", "/evaluation/dashboard", None),
            ("POST", "/evaluation/runs", None),
            ("GET", "/exports/workspace", None),
            ("GET", "/metrics/summary", None),
        )

        for role in ("uploader", "reviewer"):
            headers = session_headers(
                self.client,
                actor=f"{role}-user",
                role=role,
            )
            for method, path, payload in admin_only_requests:
                with self.subTest(role=role, method=method, path=path):
                    response = self.client.request(
                        method,
                        path,
                        headers=headers,
                        json=payload,
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["detail"], "Forbidden")

    def test_claimed_admin_role_without_admin_flag_is_denied(self) -> None:
        headers = session_headers(
            self.client,
            actor="fake-admin",
            role="admin",
            is_admin=False,
        )

        response = self.client.get("/system/dashboard", headers=headers)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Forbidden")

    def test_uploader_keeps_authenticated_invoice_intake_access(self) -> None:
        headers = session_headers(
            self.client,
            actor="invoice-uploader",
            user_id="invoice-uploader",
            role="uploader",
        )

        upload = self.client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        documents = self.client.get("/documents", headers=headers)
        invoices = self.client.get("/invoices", headers=headers)

        self.assertEqual(upload.status_code, 200)
        self.assertEqual(documents.status_code, 200)
        self.assertEqual(len(documents.json()), 1)
        self.assertEqual(invoices.status_code, 200)
        self.assertEqual(invoices.json()["total"], 1)


if __name__ == "__main__":
    unittest.main()
