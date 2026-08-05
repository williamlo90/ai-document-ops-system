from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


class HttpSecurityTests(unittest.TestCase):
    def test_session_cookie_is_opaque_and_http_only(self) -> None:
        client = TestClient(create_app(Settings(admin_token="top-secret")))
        response = client.post("/auth/session", json={"access_token": "top-secret"})
        cookie = response.headers["set-cookie"]
        self.assertNotIn("top-secret", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)

    def test_caller_identity_headers_are_ignored(self) -> None:
        client = TestClient(create_app(Settings(uploader_token="upload", workspace_id="alpha")))
        response = client.post("/auth/session", json={"access_token": "upload"}, headers={"X-Role": "admin", "X-Workspace-Id": "forged"})
        self.assertEqual(response.json()["role"], "uploader")
        self.assertEqual(response.json()["workspace_id"], "alpha")

    def test_security_headers_and_no_store_are_set(self) -> None:
        response = TestClient(create_app()).get("/auth/session")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["cache-control"], "no-store, private")

    def test_rate_limit_and_hosted_csrf_are_enforced(self) -> None:
        client = TestClient(create_app(Settings(rate_limit_requests=1)))
        client.get("/meta")
        self.assertEqual(client.get("/meta").status_code, 429)
        hosted = TestClient(create_app(Settings(environment="production", admin_token="strong-token")))
        login = hosted.post("/auth/session", json={"access_token": "strong-token"})
        cookie = login.cookies["invoice_review_session"]
        cookie_header = {"Cookie": f"invoice_review_session={cookie}"}
        self.assertEqual(hosted.delete("/auth/session", headers=cookie_header).status_code, 403)
        self.assertEqual(hosted.delete("/auth/session", headers={**cookie_header, "Origin": "http://testserver"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
