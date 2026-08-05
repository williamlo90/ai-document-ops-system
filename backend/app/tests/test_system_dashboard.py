from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.documents.status import DocumentStatus
from app.main import create_app


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class SystemDashboardTests(unittest.TestCase):
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
        self.client.close()
        self.temp_dir.cleanup()

    def test_dashboard_requires_administrator_access(self) -> None:
        self.assertEqual(self.client.get("/system/dashboard").status_code, 401)

    def test_empty_dashboard_reports_current_checks_without_fake_uptime(self) -> None:
        response = self.client.get("/system/dashboard", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overall"]["status"], "operational")
        self.assertEqual(payload["kpis"]["processing_now"], 0)
        self.assertTrue(all(service["uptime"] is None for service in payload["services"]))
        self.assertTrue(
            all(service["uptime_label"] == "Not enough history" for service in payload["services"])
        )
        self.assertIn("Unique invoices", payload["flow"]["denominator"])

    def test_completed_invoice_reconciles_job_and_flow_counts(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        processed = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)

        self.assertEqual(processed.status_code, 200)
        payload = self.client.get("/system/dashboard", headers=HEADERS).json()
        stages = {stage["id"]: stage for stage in payload["flow"]["stages"]}
        self.assertEqual(payload["kpis"]["completed_today"], 1)
        self.assertEqual(stages["upload"]["count"], 1)
        self.assertEqual(stages["read"]["count"], 1)
        self.assertEqual(stages["extract"]["count"], 1)
        self.assertEqual(stages["checks"]["count"], 1)
        self.assertEqual(stages["read"]["conversion_percent"], 100.0)
        self.assertEqual(payload["recent_jobs"][0]["document_id"], document_id)

    def test_failed_job_detail_is_sanitized_and_retryable_only_when_state_allows(self) -> None:
        upload = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("private-invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        container = self.client.app.state.container
        document = container.documents.get(UUID(upload.json()["document"]["id"]))
        job = container.jobs.get_latest_for_document(document.id)
        job.start()
        job.fail("secret-payload customer@example.com")
        container.jobs.save(job)
        document.status = DocumentStatus.FAILED
        container.documents.add(document)

        payload = self.client.get("/system/dashboard", headers=HEADERS).json()

        self.assertEqual(payload["kpis"]["needs_attention"], 1)
        self.assertNotIn("customer@example.com", str(payload))
        self.assertTrue(payload["recent_jobs"][0]["retryable"])
        self.assertEqual(
            payload["recent_jobs"][0]["failure_summary"],
            "Invoice processing did not complete.",
        )


if __name__ == "__main__":
    unittest.main()
