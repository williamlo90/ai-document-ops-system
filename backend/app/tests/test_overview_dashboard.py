from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.validation.invoice import validate_invoice


ADMIN_TOKEN = "overview-admin-token"
REVIEWER_TOKEN = "overview-reviewer-token"
UPLOADER_TOKEN = "overview-uploader-token"
ADMIN_HEADERS = {"X-Access-Token": ADMIN_TOKEN}
REVIEWER_HEADERS = {"X-Access-Token": REVIEWER_TOKEN}
UPLOADER_HEADERS = {"X-Access-Token": UPLOADER_TOKEN}


class OverviewDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = TestClient(
            create_app(
                Settings(
                    app_env="test",
                    admin_token=ADMIN_TOKEN,
                    reviewer_token=REVIEWER_TOKEN,
                    uploader_token=UPLOADER_TOKEN,
                    upload_root=Path(self.temp_dir.name),
                    max_upload_bytes=1000,
                )
            )
        )

    def tearDown(self) -> None:
        self.client.close()
        self.temp_dir.cleanup()

    def test_dashboard_requires_review_access(self) -> None:
        self.assertEqual(self.client.get("/overview/dashboard").status_code, 401)
        self.assertEqual(
            self.client.get("/overview/dashboard", headers=UPLOADER_HEADERS).status_code,
            403,
        )

    def test_empty_reviewer_dashboard_is_honest_and_has_no_export_surface(self) -> None:
        response = self.client.get("/overview/dashboard", headers=REVIEWER_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        payload = response.json()
        self.assertEqual(payload["briefing"]["attention_count"], 0)
        self.assertFalse(payload["capabilities"]["export_access"])
        self.assertFalse(payload["capabilities"]["sla_policy"])
        self.assertNotIn("ready_export", {item["id"] for item in payload["kpis"]})
        self.assertEqual(len(payload["throughput"]["points"]), 7)
        self.assertTrue(
            all(
                point["processed"] == 0 and point["sent_for_review"] == 0
                for point in payload["throughput"]["points"]
            )
        )
        self.assertNotIn("SLA", str(payload))

    def test_admin_counts_reconcile_with_canonical_workspaces(self) -> None:
        approved_id = self._upload_and_process("approved.pdf")
        blocked_id = self._upload_and_process("blocked.pdf")
        self._upload_and_process("waiting.pdf")
        self._add_missing_invoice_number(blocked_id)

        approved = self.client.post(f"/review/{approved_id}/approve", headers=REVIEWER_HEADERS)
        self.assertEqual(approved.status_code, 200)

        overview_response = self.client.get("/overview/dashboard", headers=ADMIN_HEADERS)
        self.assertEqual(overview_response.status_code, 200)
        overview = overview_response.json()
        invoices = self.client.get("/invoices?page_size=100", headers=ADMIN_HEADERS).json()
        worklist = self.client.get("/review/worklist?page_size=100", headers=ADMIN_HEADERS).json()
        exceptions = self.client.get("/exceptions?page_size=100", headers=ADMIN_HEADERS).json()
        exports = self.client.get("/exports/workspace?page_size=100", headers=ADMIN_HEADERS).json()
        kpis = {item["id"]: item["count"] for item in overview["kpis"]}

        self.assertEqual(overview["queue"]["total"], worklist["total"])
        self.assertEqual(kpis["waiting_review"], invoices["summary"]["waiting_review"])
        self.assertEqual(kpis["needs_correction"], invoices["summary"]["needs_correction"])
        self.assertEqual(kpis["ready_export"], exports["summary"]["ready"]["count"])
        self.assertEqual(
            overview["exception_breakdown"]["total"],
            exceptions["summary"]["open_exceptions"],
        )
        self.assertEqual(overview["recent_decisions"][0]["title"], "Invoice approved")
        self.assertEqual(overview["recent_decisions"][0]["actor"], "Invoice Reviewer")
        self.assertEqual(
            sum(point["processed"] for point in overview["throughput"]["points"]),
            3,
        )
        self.assertTrue(overview["capabilities"]["export_access"])

    def test_reviewer_dashboard_does_not_leak_admin_export_counts(self) -> None:
        approved_id = self._upload_and_process("approved.pdf")
        self.client.post(f"/review/{approved_id}/approve", headers=REVIEWER_HEADERS)

        payload = self.client.get("/overview/dashboard", headers=REVIEWER_HEADERS).json()
        kpis = {item["id"]: item for item in payload["kpis"]}

        self.assertIn("approved", kpis)
        self.assertNotIn("ready_export", kpis)
        self.assertFalse(any("/exports" in alert["href"] for alert in payload["alerts"]))

    def _upload_and_process(self, filename: str) -> str:
        uploaded = self.client.post(
            "/documents/upload",
            headers=ADMIN_HEADERS,
            files={"file": (filename, b"%PDF- invoice", "application/pdf")},
        )
        self.assertEqual(uploaded.status_code, 200)
        document_id = uploaded.json()["document"]["id"]
        processed = self.client.post(f"/documents/{document_id}/process", headers=ADMIN_HEADERS)
        self.assertEqual(processed.status_code, 200)
        return document_id

    def _add_missing_invoice_number(self, document_id: str) -> None:
        container = self.client.app.state.container
        stored = container.extractions.get_for_document(UUID(document_id))
        data = replace(
            stored.extraction_result.extraction.data,
            invoice_number=None,
        )
        extraction = replace(stored.extraction_result.extraction, data=data)
        container.extractions.save(
            UUID(document_id),
            replace(stored.extraction_result, extraction=extraction),
            validate_invoice(data),
        )


if __name__ == "__main__":
    unittest.main()
