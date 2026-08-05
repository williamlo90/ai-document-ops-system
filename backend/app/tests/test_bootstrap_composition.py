from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.bootstrap.container import AppContainer
from app.core.settings import Settings
from app.main import create_app


class BootstrapCompositionTests(unittest.TestCase):
    def test_app_owns_explicit_container(self) -> None:
        app = create_app(Settings(environment="test", database_ready=False, storage_ready=True))
        self.assertIsInstance(app.state.container, AppContainer)
        self.assertEqual(app.state.container.readiness(), {"database": False, "storage": True})

    def test_problem_response_reuses_request_identifier(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/meta/missing", headers={"x-request-id": "req-123"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["x-request-id"], "req-123")
        self.assertEqual(response.json()["request_id"], "req-123")


if __name__ == "__main__":
    unittest.main()
