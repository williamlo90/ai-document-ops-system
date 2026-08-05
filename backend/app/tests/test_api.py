from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class ApiTests(unittest.TestCase):
    def test_health_reports_process_liveness(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_reports_introduced_dependency_checks(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "checks": {
                    "lifecycle": "ready",
                    "database": "ready",
                    "storage": "ready",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
