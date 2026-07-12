from __future__ import annotations

import json
import logging
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.core.observability import HttpMetrics, JsonFormatter
from app.core.settings import Settings
from app.main import create_app


class RuntimeObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(
            create_app(
                Settings(
                    app_env="test",
                    admin_token="test-token",
                    upload_root=Path("backend/data/test-observability"),
                    max_upload_bytes=1024,
                )
            )
        )

    def test_correlation_headers_preserve_traceparent(self) -> None:
        response = self.client.get(
            "/health",
            headers={
                "X-Request-ID": "request-123",
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            },
        )
        self.assertEqual(response.headers["X-Request-ID"], "request-123")
        self.assertEqual(response.headers["X-Trace-ID"], "4bf92f3577b34da6a3ce929d0e0e4736")

    def test_prometheus_endpoint_contains_request_counter(self) -> None:
        self.client.get("/health")
        response = self.client.get("/internal/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("docintel_http_requests_total", response.text)
        self.assertIn('route="/health"', response.text)

    def test_not_ready_uses_service_unavailable(self) -> None:
        self.client.app.state.accepting_traffic = False
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["lifecycle"], "stopping")

    def test_json_formatter_emits_context(self) -> None:
        record = logging.LogRecord(
            "docintel.http", logging.INFO, __file__, 1, "request_completed", (), None
        )
        record.request_id = "request-1"
        record.status_code = 200
        payload = json.loads(JsonFormatter().format(record))
        self.assertEqual(payload["request_id"], "request-1")
        self.assertEqual(payload["status_code"], 200)

    def test_metrics_registry_is_prometheus_compatible(self) -> None:
        metrics = HttpMetrics()
        metrics.observe("GET", "/health", 200, 0.125)
        payload = metrics.prometheus()
        self.assertIn('route="/health",status="200"} 1', payload)
        self.assertIn(" 0.125000", payload)


if __name__ == "__main__":
    unittest.main()
