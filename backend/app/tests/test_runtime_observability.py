from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


class RuntimeObservabilityTests(unittest.TestCase):
    def test_request_id_is_preserved_and_metrics_are_recorded(self) -> None:
        app = create_app()
        with TestClient(app) as client:
            response = client.get("/health", headers={"x-request-id": "trace-123"})
            summary = client.get("/internal/runtime-summary")

        self.assertEqual(response.headers["x-request-id"], "trace-123")
        self.assertGreaterEqual(summary.json()["metrics"]["requests"], 1)

    def test_readiness_failure_does_not_change_liveness(self) -> None:
        app = create_app(Settings(database_ready=False))
        with TestClient(app) as client:
            ready = client.get("/ready")
            health = client.get("/health")

        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["checks"]["database"], "unavailable")
        self.assertEqual(health.status_code, 200)


if __name__ == "__main__":
    unittest.main()
