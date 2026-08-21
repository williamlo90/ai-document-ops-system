from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
from typing import Any
import unittest

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.integrations.erpnext_adapter import ERPNextPurchaseInvoiceAdapter
from app.integrations.models import IntegrationDeliveryError
from app.main import create_app


HEADERS = {"X-Admin-Token": "test-token"}


class FakeERPNextClient:
    def __init__(self, *, lose_create_response: bool = False, docstatus: int = 0) -> None:
        self.lose_create_response = lose_create_response
        self.docstatus = docstatus
        self.create_count = 0
        self.documents: dict[str, dict[str, Any]] = {}

    def create_purchase_invoice(self, values: dict[str, Any]) -> dict[str, Any]:
        self.create_count += 1
        name = "ACC-PINV-2026-00001"
        document = {
            **deepcopy(values),
            "name": name,
            "grand_total": "110.00",
            "docstatus": self.docstatus,
            "modified": "2026-08-14 08:00:00.000000",
        }
        self.documents[name] = document
        if self.lose_create_response:
            self.lose_create_response = False
            raise IntegrationDeliveryError(
                "ERPNext may have saved the draft before the connection closed",
                code="erpnext_create_outcome_unknown",
                retryable=True,
                outcome_unknown=True,
            )
        return deepcopy(document)

    def find_purchase_invoices_by_delivery_key(self, delivery_key: str) -> list[dict[str, Any]]:
        return [
            {"name": name, "docstatus": document["docstatus"]}
            for name, document in self.documents.items()
            if document.get("custom_invoice_review_delivery_key") == delivery_key
        ]

    def get_purchase_invoice(self, name: str) -> dict[str, Any]:
        return deepcopy(self.documents[name])

    def document_url(self, name: str) -> str:
        return f"http://127.0.0.1:8080/app/purchase-invoice/{name}"


class ERPNextAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token="test-token",
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
            accounting_provider="erpnext",
            erpnext_api_key="fake-key",
            erpnext_api_secret="fake-secret",
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.client.app.state.container.close()
        self.temp_dir.cleanup()

    def test_creates_one_verified_draft_and_replays_without_a_second_post(self) -> None:
        provider = FakeERPNextClient()
        self._use_provider(provider)
        document_id = self._approved_document()

        ready = self.client.get(
            f"/integrations/erpnext/documents/{document_id}/delivery",
            headers=HEADERS,
        )
        first = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )
        replay = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["delivery"]["status"], "ready")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["delivery"]["status"], "succeeded")
        self.assertEqual(first.json()["delivery"]["provider_docstatus"], 0)
        self.assertFalse(first.json()["delivery"]["replayed"])
        self.assertTrue(replay.json()["delivery"]["replayed"])
        self.assertEqual(provider.create_count, 1)

        workspace = self.client.get(
            "/exports/workspace?view=exported",
            headers=HEADERS,
        ).json()
        row = next(item for item in workspace["items"] if item["id"] == document_id)
        self.assertEqual(row["erp_delivery"]["status"], "succeeded")
        self.assertIn("/app/purchase-invoice/", row["erp_delivery"]["external_url"])

    def test_unknown_create_outcome_reconciles_by_server_delivery_key(self) -> None:
        provider = FakeERPNextClient(lose_create_response=True)
        self._use_provider(provider)
        document_id = self._approved_document()

        create = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )
        unknown = self.client.get(
            f"/integrations/erpnext/documents/{document_id}/delivery",
            headers=HEADERS,
        )
        reconciled = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/delivery/reconcile",
            headers=HEADERS,
        )

        self.assertEqual(create.status_code, 502)
        self.assertTrue(create.json()["detail"]["outcome_unknown"])
        self.assertEqual(unknown.json()["delivery"]["status"], "unknown")
        self.assertEqual(reconciled.status_code, 200)
        self.assertEqual(reconciled.json()["delivery"]["status"], "succeeded")
        self.assertEqual(provider.create_count, 1)

    def test_rejects_non_draft_provider_receipt_and_records_safety_event(self) -> None:
        provider = FakeERPNextClient(docstatus=1)
        self._use_provider(provider)
        document_id = self._approved_document()

        response = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "erpnext_unsafe_state")
        events = self.client.get(f"/documents/{document_id}", headers=HEADERS).json()[
            "audit_events"
        ]
        self.assertIn(
            "erp_draft_unsafe_state_detected",
            [event["event_type"] for event in events],
        )

    def test_blocks_unapproved_document_before_calling_erpnext(self) -> None:
        provider = FakeERPNextClient()
        self._use_provider(provider)
        document_id = self._processed_document()

        response = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(provider.create_count, 0)
        events = self.client.get(f"/documents/{document_id}", headers=HEADERS).json()[
            "audit_events"
        ]
        self.assertIn("erp_draft_blocked", [event["event_type"] for event in events])

    def test_blocks_invalid_mapping_before_calling_erpnext(self) -> None:
        provider = FakeERPNextClient()
        self._use_provider(provider)
        document_id = self._processed_document()
        saved = self.client.post(
            f"/review/{document_id}/save",
            headers=HEADERS,
            json={
                "notes": "Verify unmapped supplier handling",
                "corrected_data": {
                    "vendor_name": "Supplier Without ERP Mapping",
                    "invoice_number": "PHASE7-INVALID-MAPPING",
                    "invoice_date": "2026-07-01",
                    "due_date": "2026-07-31",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "110.00",
                    "currency": "USD",
                },
            },
        )
        approved = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        response = self.client.post(
            f"/integrations/erpnext/documents/{document_id}/draft",
            headers=HEADERS,
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(response.status_code, 422)
        self.assertIn("supplier mapping", response.json()["detail"])
        self.assertEqual(provider.create_count, 0)
        events = self.client.get(f"/documents/{document_id}", headers=HEADERS).json()[
            "audit_events"
        ]
        self.assertIn("erp_draft_blocked", [event["event_type"] for event in events])

    def test_erpnext_routes_expose_no_submit_or_payment_action(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        exposed = {
            (method.upper(), path)
            for path, operations in paths.items()
            if path.startswith("/integrations/erpnext")
            for method in operations
        }

        self.assertEqual(
            exposed,
            {
                ("GET", "/integrations/erpnext/documents/{document_id}/delivery"),
                ("POST", "/integrations/erpnext/documents/{document_id}/draft"),
                (
                    "POST",
                    "/integrations/erpnext/documents/{document_id}/delivery/reconcile",
                ),
            },
        )
        self.assertFalse(
            any(
                forbidden in path.casefold()
                for _, path in exposed
                for forbidden in ("submit", "post", "pay", "payment")
            )
        )

    def test_erpnext_logs_exclude_credentials_and_invoice_payload(self) -> None:
        provider = FakeERPNextClient()
        self._use_provider(provider)
        document_id = self._processed_document()
        saved = self.client.post(
            f"/review/{document_id}/save",
            headers=HEADERS,
            json={
                "notes": "Prepare known values for log redaction test",
                "corrected_data": {
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "PHASE7-SENSITIVE-INVOICE",
                    "invoice_date": "2026-07-01",
                    "due_date": "2026-07-31",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "110.00",
                    "currency": "USD",
                },
            },
        )
        approved = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)

        with self.assertLogs("docintel", level="INFO") as captured:
            response = self.client.post(
                f"/integrations/erpnext/documents/{document_id}/draft",
                headers=HEADERS,
            )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(response.status_code, 200)
        logs = "\n".join(captured.output)
        for sensitive in (
            "fake-key",
            "fake-secret",
            "Acme Logistics",
            "PHASE7-SENSITIVE-INVOICE",
            "100.00",
            "110.00",
        ):
            with self.subTest(sensitive=sensitive):
                self.assertNotIn(sensitive, logs)

    def _use_provider(self, provider: FakeERPNextClient) -> None:
        adapter = ERPNextPurchaseInvoiceAdapter(provider)
        service = self.client.app.state.container.integration_service
        service.adapter = adapter
        service.delivery_executor.adapter = adapter

    def _approved_document(self) -> str:
        document_id = self._processed_document()
        approved = self.client.post(f"/review/{document_id}/approve", headers=HEADERS)
        self.assertEqual(approved.status_code, 200)
        return document_id

    def _processed_document(self) -> str:
        uploaded = self.client.post(
            "/documents/upload",
            headers=HEADERS,
            files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
        )
        document_id = str(uploaded.json()["document"]["id"])
        processed = self.client.post(f"/documents/{document_id}/process", headers=HEADERS)
        self.assertEqual(processed.status_code, 200)
        return document_id


if __name__ == "__main__":
    unittest.main()
