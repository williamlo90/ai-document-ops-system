from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.security import SecurityContext, SessionStore
from app.core.settings import Settings
from app.core.upload_scanning import SignatureUploadScanner
from app.main import create_app
from app.providers.storage import StorageError


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "local",
        "admin_token": "test-token",
        "upload_root": Path("uploads"),
        "max_upload_bytes": 1_000,
        "rate_limit_requests": 120,
        "rate_limit_window_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class SessionSecurityTests(unittest.TestCase):
    def test_session_is_opaque_and_revocable(self) -> None:
        store = SessionStore(ttl_seconds=60)
        context = SecurityContext(actor="operator")
        session_id = store.create(context)
        self.assertNotIn("operator", session_id)
        self.assertEqual(store.get(session_id), context)
        store.revoke(session_id)
        self.assertIsNone(store.get(session_id))

    def test_ui_cookie_does_not_contain_admin_credential(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(
                create_app(settings(upload_root=Path(temp_dir), admin_token="top-secret-token"))
            )
            response = client.post(
                "/ui/login",
                data={"admin_token": "top-secret-token"},
                follow_redirects=False,
            )
            cookie = response.headers["set-cookie"]
            self.assertNotIn("top-secret-token", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=strict", cookie)

    def test_json_session_authenticates_api_without_browser_stored_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(create_app(settings(upload_root=Path(temp_dir))))
            login = client.post("/auth/session", json={"admin_token": "test-token"})

            self.assertEqual(login.status_code, 200)
            self.assertTrue(login.json()["authenticated"])
            self.assertIn("httponly", login.headers["set-cookie"].lower())
            self.assertEqual(client.get("/backoffice/workspace").status_code, 200)

            self.assertEqual(client.delete("/auth/session").status_code, 200)
            self.assertEqual(client.get("/auth/session").status_code, 401)


class HttpMiddlewareTests(unittest.TestCase):
    def test_security_headers_are_set(self) -> None:
        client = TestClient(create_app(settings()))
        response = client.get("/health")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-src 'self' blob:", response.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_document_content_can_be_embedded_by_same_origin_preview(self) -> None:
        client = TestClient(create_app(settings()))
        for path in ("/documents/example/content", "/ui/documents/example/preview"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")
                self.assertIn("frame-ancestors 'self'", response.headers["content-security-policy"])
                self.assertNotIn("frame-ancestors 'none'", response.headers["content-security-policy"])

    def test_rate_limit_returns_429(self) -> None:
        client = TestClient(create_app(settings(rate_limit_requests=1)))
        self.assertEqual(client.get("/documents").status_code, 401)
        response = client.get("/documents")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_production_cookie_request_requires_same_origin(self) -> None:
        strong_token = "a-production-token-with-24-characters"
        with tempfile.TemporaryDirectory() as temp_dir:
            client = TestClient(
                create_app(
                    settings(
                        app_env="production",
                        admin_token=strong_token,
                        upload_root=Path(temp_dir),
                    )
                )
            )
            login = client.post(
                "/ui/login", data={"admin_token": strong_token}, follow_redirects=False
            )
            self.assertEqual(login.status_code, 303)
            cookie_header = {
                "Cookie": f"doc_intel_admin_token={client.cookies['doc_intel_admin_token']}"
            }
            rejected = client.post("/ui/logout", headers=cookie_header, follow_redirects=False)
            self.assertEqual(rejected.status_code, 403)
            accepted = client.post(
                "/ui/logout",
                headers={**cookie_header, "Origin": "http://testserver"},
                follow_redirects=False,
            )
            self.assertEqual(accepted.status_code, 303)


class UploadScannerTests(unittest.TestCase):
    def test_scanner_rejects_signature_across_chunk_boundary(self) -> None:
        scanner = SignatureUploadScanner()
        with self.assertRaises(StorageError):
            list(scanner.scan([b"%PDF-EICAR-STANDARD-", b"ANTIVIRUS-TEST-FILE"]))


if __name__ == "__main__":
    unittest.main()
