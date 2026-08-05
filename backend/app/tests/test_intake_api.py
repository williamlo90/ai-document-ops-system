from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


class IntakeApiTests(unittest.TestCase):
    def test_uploader_can_intake_and_read_same_workspace_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(create_app(Settings(upload_root=Path(temp_dir), workspace_id="alpha")))
            client.post("/auth/session", json={"access_token": "local-uploader"})
            upload = client.post("/documents/intake?filename=invoice.pdf", content=b"%PDF-invoice", headers={"content-type": "application/pdf"})
            self.assertEqual(upload.status_code, 200)
            self.assertEqual(upload.json()["workspace_id"], "alpha")
            content = client.get(f"/documents/{upload.json()['id']}/content")
            self.assertEqual(content.content, b"%PDF-invoice")
            self.assertEqual(content.headers["x-frame-options"], "SAMEORIGIN")

    def test_reviewer_cannot_upload_and_anonymous_cannot_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(Settings(upload_root=Path(temp_dir)))
            reviewer = TestClient(app)
            reviewer.post("/auth/session", json={"access_token": "local-reviewer"})
            self.assertEqual(reviewer.post("/documents/intake?filename=invoice.pdf", content=b"%PDF-invoice").status_code, 403)
            self.assertEqual(TestClient(app).get("/documents/00000000-0000-0000-0000-000000000000/content").status_code, 401)

    def test_clamav_profile_fails_closed_when_scanner_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(create_app(Settings(upload_root=Path(temp_dir), scanner_profile="clamav")))
            client.post("/auth/session", json={"access_token": "local-uploader"})
            with self.assertRaises(Exception):
                client.post("/documents/intake?filename=invoice.pdf", content=b"%PDF-invoice")


if __name__ == "__main__":
    unittest.main()
