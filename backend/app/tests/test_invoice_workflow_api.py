from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.main import create_app
from app.review.datasets import sample_invoice


class InvoiceWorkflowApiTests(unittest.TestCase):
    def test_reviewer_corrects_and_approves_with_auditable_state(self) -> None:
        app = create_app()
        document = DocumentRecord("invoice.pdf", "key", "application/pdf", status=DocumentStatus.NEEDS_REVIEW)
        with app.state.container.persistence.transactions.transaction():
            app.state.container.persistence.documents.add(document)
        app.state.container.review_module.service.seed(document.id, sample_invoice(total="111.00"))
        client = TestClient(app)
        client.post("/auth/session", json={"access_token": "local-reviewer"})
        blocked = client.post(f"/review/{document.id}/approve", json={"note": "Checked"})
        self.assertEqual(blocked.status_code, 409)
        corrected = client.patch(f"/review/{document.id}/correction", json={"field_name": "total", "value": "110.00", "reason": "Matched PDF"})
        self.assertEqual(corrected.status_code, 200)
        approved = client.post(f"/review/{document.id}/approve", json={"note": "Verified"})
        self.assertEqual(approved.json()["status"], "approved")
        workflow = client.get(f"/invoices/{document.id}/workflow").json()
        self.assertEqual((workflow["status"], workflow["correction_count"]), ("approved", 1))


if __name__ == "__main__":
    unittest.main()
