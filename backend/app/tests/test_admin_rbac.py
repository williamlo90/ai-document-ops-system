from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class AdminRbacTests(unittest.TestCase):
    def test_protected_routes_require_session_and_role(self) -> None:
        client = TestClient(create_app())
        self.assertEqual(client.get("/workspace").status_code, 401)
        client.post("/auth/session", json={"access_token": "local-reviewer"})
        self.assertEqual(client.get("/workspace").status_code, 200)
        self.assertEqual(client.get("/admin/runtime").status_code, 403)

    def test_admin_session_can_read_admin_runtime(self) -> None:
        client = TestClient(create_app())
        client.post("/auth/session", json={"access_token": "local-admin"})
        self.assertEqual(client.get("/admin/runtime").status_code, 200)


if __name__ == "__main__":
    unittest.main()
