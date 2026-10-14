from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult
from app.validation.invoice import validate_invoice
from app.documents.status import DocumentStatus
from decimal import Decimal


class EvidenceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = Settings(
            "test",
            "admin-token",
            Path(self.temp.name),
            10000,
            reviewer_token="reviewer-token",
            ap_approver_token="approver-token",
            storage_backend="sqlite",
            sqlite_path=Path(self.temp.name) / "db",
        )
        self.app = create_app(settings)
        self.client = TestClient(self.app)
        self.addCleanup(self.app.state.container.close)
        self.container = self.app.state.container
        self.doc = DocumentRecord(
            original_filename="a.pdf",
            storage_key="a.pdf",
            content_type="application/pdf",
            status=DocumentStatus.NEEDS_REVIEW,
        )
        self.container.documents.save(self.doc)
        self.invoice = InvoiceData(
            vendor_name="Acme",
            line_items=(
                InvoiceLineItem(description="Item", uom="EA", line_id="l1", quantity=Decimal("1")),
            ),
        )
        self.container.extractions.save(
            self.doc.id,
            ExtractionResult(InvoiceExtraction(self.invoice), "mock"),
            validate_invoice(self.invoice),
        )
        self.path = f"/ap/invoices/{self.doc.id}"

    def headers(self, role):
        return {"X-Access-Token": f"{role}-token"}

    def test_capture_attest_roundtrip_and_scope(self):
        self.assertEqual(self.client.get(self.path).status_code, 401)
        initial = self.client.post(self.path + "/capture", headers=self.headers("reviewer"))
        self.assertEqual(initial.status_code, 200, initial.text)
        version = initial.json()["version"]
        result = self.client.put(
            self.path + "/evidence",
            headers=self.headers("reviewer"),
            json={
                "expected_revision": version,
                "reason": "Checked PDF",
                "fields": {
                    "vendor_name": {
                        "kind": "observed",
                        "raw": "Acme",
                        "normalized": "Acme",
                        "effective": "Acme",
                        "page": 2,
                        "excerpt": "Acme",
                    }
                },
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        view = self.client.get(self.path, headers=self.headers("approver")).json()
        self.assertEqual(view["current"]["fields"]["vendor_name"]["page"], 2)
        self.assertTrue(view["capabilities"]["approve"])
        self.assertFalse(view["capabilities"]["review"])
        self.assertEqual(
            self.client.post(self.path + "/capture", headers=self.headers("approver")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/ap/sources/import", headers=self.headers("reviewer"), json={"records": []}
            ).status_code,
            422,
        )
        other = DocumentRecord(
            original_filename="other.pdf",
            storage_key="other.pdf",
            content_type="application/pdf",
            workspace_id="other",
        )
        self.container.documents.save(other)
        self.assertEqual(
            self.client.get(f"/ap/invoices/{other.id}", headers=self.headers("admin")).status_code,
            404,
        )

    def test_legacy_correction_retains_uom_and_revision_diff(self):
        self.client.post(self.path + "/capture", headers=self.headers("reviewer"))
        response = self.client.post(
            f"/review/{self.doc.id}/save",
            headers=self.headers("reviewer"),
            json={
                "notes": "Corrected line from PDF",
                "corrected_data": {
                    "vendor_name": "Acme corrected",
                    "line_items": [
                        {"line_id": "l1", "description": "Item", "uom": "BOX", "quantity": "2"}
                    ],
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        view = self.client.get(self.path, headers=self.headers("reviewer")).json()
        self.assertEqual(len(view["history"]), 2)
        self.assertEqual(view["current"]["fields"]["lines.l1.uom"]["effective"], "BOX")
        self.assertEqual(view["current"]["fields"]["lines.l1.uom"]["kind"], "unknown")
        self.assertEqual(view["history"][0]["fields"]["lines.l1.uom"]["effective"], "EA")
        self.assertIn("lines.l1.uom", view["current"]["changes"])
