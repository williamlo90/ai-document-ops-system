from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


TOKEN = "test-token"
PDF = b"%PDF-1.4\nintake test\n%%EOF"


class IntakeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name) / "uploads",
            max_upload_bytes=1000,
            storage_backend="memory",
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_upload_policy_metadata_and_preview_are_workspace_scoped(self) -> None:
        headers = {
            "X-Admin-Token": TOKEN,
            "X-User-Id": "William Lo",
            "X-Workspace-Id": "alpha",
        }
        upload = self.client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
        )

        self.assertEqual(upload.status_code, 200)
        document = upload.json()["document"]
        self.assertEqual(document["submitted_by"], "William Lo")
        self.assertEqual(document["size_bytes"], len(PDF))

        policy = self.client.get(
            f"/documents/upload-policy?filename=invoice.pdf&size_bytes={len(PDF)}",
            headers=headers,
        )
        self.assertEqual(policy.status_code, 200)
        self.assertEqual(policy.json()["max_upload_bytes"], 1000)
        self.assertEqual(len(policy.json()["duplicates"]), 1)

        preview = self.client.get(f"/documents/{document['id']}/content", headers=headers)
        hidden = self.client.get(
            f"/documents/{document['id']}/content",
            headers={**headers, "X-Workspace-Id": "beta"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers["content-type"], "application/pdf")
        self.assertEqual(preview.content, PDF)
        self.assertEqual(hidden.status_code, 404)

    def test_invoice_list_filters_submitter_status_and_paginates(self) -> None:
        base = {"X-Admin-Token": TOKEN, "X-Workspace-Id": "alpha"}
        for index, user in enumerate(("William Lo", "Other Operator", "William Lo")):
            response = self.client.post(
                "/documents/upload",
                headers={**base, "X-User-Id": user},
                files={"file": (f"invoice-{index}.pdf", PDF, "application/pdf")},
            )
            self.assertEqual(response.status_code, 200)

        mine = self.client.get(
            "/invoices?submitted_by=William%20Lo&page=1&page_size=1",
            headers=base,
        )
        queued = self.client.get("/invoices?status=queued", headers=base)
        searched = self.client.get("/invoices?search=invoice-1", headers=base)
        today = datetime.now(UTC).date()
        dated = self.client.get(f"/invoices?created_from={today}&created_to={today}", headers=base)
        future = self.client.get(
            f"/invoices?created_from={today + timedelta(days=1)}",
            headers=base,
        )

        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["total"], 2)
        self.assertEqual(mine.json()["total_pages"], 2)
        self.assertEqual(len(mine.json()["items"]), 1)
        self.assertEqual(queued.json()["total"], 3)
        self.assertEqual(searched.json()["total"], 1)
        self.assertEqual(searched.json()["items"][0]["submitted_by"], "Other Operator")
        self.assertEqual(dated.json()["total"], 3)
        self.assertEqual(future.json()["total"], 0)

    def test_invoice_list_searches_extracted_fields_and_surfaces_correction_status(self) -> None:
        headers = {"X-Admin-Token": TOKEN, "X-User-Id": "William Lo"}
        document_ids: list[str] = []
        for filename in ("first.pdf", "copy.pdf"):
            upload = self.client.post(
                "/documents/upload",
                headers=headers,
                files={"file": (filename, PDF, "application/pdf")},
            )
            document_id = upload.json()["document"]["id"]
            self.client.post(f"/documents/{document_id}/process", headers=headers)
            document_ids.append(document_id)

        vendor_search = self.client.get("/invoices?search=acme%20logistics", headers=headers)
        number_search = self.client.get("/invoices?search=inv-001", headers=headers)
        correction_filter = self.client.get("/invoices?status=needs_correction", headers=headers)

        self.assertEqual(vendor_search.json()["total"], 2)
        self.assertEqual(number_search.json()["total"], 2)
        self.assertEqual(correction_filter.json()["total"], 1)
        item = correction_filter.json()["items"][0]
        self.assertEqual(item["id"], document_ids[1])
        self.assertEqual(item["business_status"], "needs_correction")
        self.assertTrue(item["has_validation_errors"])
        self.assertEqual(item["validation_codes"], ["duplicate_invoice"])

    def test_uploader_role_can_only_work_with_own_invoices(self) -> None:
        base = {"X-Admin-Token": TOKEN, "X-Workspace-Id": "alpha"}
        william_headers = {
            **base,
            "X-User-Id": "William Lo",
            "X-Role": "uploader",
        }
        other_headers = {
            **base,
            "X-User-Id": "Other Operator",
            "X-Role": "uploader",
        }
        reviewer_headers = {
            **base,
            "X-User-Id": "Finance Reviewer",
            "X-Role": "reviewer",
        }

        william_upload = self.client.post(
            "/documents/upload",
            headers=william_headers,
            files={"file": ("william.pdf", PDF, "application/pdf")},
        )
        other_upload = self.client.post(
            "/documents/upload",
            headers=other_headers,
            files={"file": ("other.pdf", PDF, "application/pdf")},
        )
        reviewer_upload = self.client.post(
            "/documents/upload",
            headers=reviewer_headers,
            files={"file": ("reviewer.pdf", PDF, "application/pdf")},
        )
        william_document_id = william_upload.json()["document"]["id"]
        other_document_id = other_upload.json()["document"]["id"]

        william_list = self.client.get("/invoices", headers=william_headers)
        william_documents = self.client.get("/documents", headers=william_headers)
        william_detail = self.client.get(f"/documents/{william_document_id}", headers=william_headers)
        hidden_detail = self.client.get(f"/documents/{other_document_id}", headers=william_headers)
        hidden_workflow = self.client.get(
            f"/documents/{other_document_id}/workflow",
            headers=william_headers,
        )
        own_process = self.client.post(
            f"/documents/{william_document_id}/process",
            headers=william_headers,
        )
        cross_process = self.client.post(
            f"/documents/{other_document_id}/process",
            headers=william_headers,
        )

        self.assertEqual(william_upload.status_code, 200)
        self.assertEqual(other_upload.status_code, 200)
        self.assertEqual(reviewer_upload.status_code, 403)
        self.assertEqual(william_list.json()["total"], 1)
        self.assertEqual(william_list.json()["items"][0]["submitted_by"], "William Lo")
        self.assertEqual(len(william_documents.json()), 1)
        self.assertEqual(william_detail.status_code, 200)
        self.assertEqual(hidden_detail.status_code, 404)
        self.assertEqual(hidden_workflow.status_code, 404)
        self.assertEqual(own_process.status_code, 200)
        self.assertEqual(cross_process.status_code, 404)

    def test_intake_draft_persists_line_items_and_revalidates_arithmetic(self) -> None:
        headers = {"X-Admin-Token": TOKEN, "X-User-Id": "William Lo"}
        upload = self.client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=headers)

        saved = self.client.post(
            f"/invoices/{document_id}/draft",
            headers=headers,
            json={
                "vendor_name": "Acme",
                "invoice_number": "INV-DRAFT",
                "invoice_date": "2026-06-29",
                "subtotal": "20",
                "tax": "2",
                "total": "22",
                "currency": "IDR",
                "line_items": [
                    {
                        "description": "Service",
                        "quantity": "2",
                        "unit_price": "10",
                        "amount": "20",
                    }
                ],
            },
        )
        detail = self.client.get(f"/documents/{document_id}", headers=headers).json()

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(detail["extraction"]["data"]["line_items"][0]["amount"], "20")
        self.assertEqual(detail["extraction"]["validation"], [])
        self.assertIn(
            "intake_draft_saved",
            [event["event_type"] for event in detail["audit_events"]],
        )

    def test_requested_correction_returns_to_reviewer_with_auditable_diff(self) -> None:
        uploader_headers = {
            "X-Admin-Token": TOKEN,
            "X-User-Id": "William Lo",
            "X-Role": "intake",
        }
        reviewer_headers = {
            "X-Admin-Token": TOKEN,
            "X-User-Id": "Rina Reviewer",
            "X-Role": "reviewer",
        }
        upload = self.client.post(
            "/documents/upload",
            headers=uploader_headers,
            files={"file": ("invoice.pdf", PDF, "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        self.client.post(f"/documents/{document_id}/process", headers=uploader_headers)
        self.client.post(
            "/backoffice/work-items",
            headers=reviewer_headers,
            json={
                "title": "Review Acme invoice",
                "work_type": "invoice_review",
                "linked_document_ids": [document_id],
                "requested_outcome": "Review invoice",
            },
        )

        requested = self.client.post(
            f"/documents/{document_id}/request-correction",
            headers=reviewer_headers,
            json={"reason": "Use the full legal vendor name from the PDF."},
        )
        uploader_workflow = self.client.get(
            f"/documents/{document_id}/workflow",
            headers=uploader_headers,
        ).json()
        corrected = self.client.post(
            f"/invoices/{document_id}/draft",
            headers=uploader_headers,
            json={
                "vendor_name": "Acme Logistics Ltd",
                "invoice_number": "INV-001",
                "invoice_date": "2026-06-18",
                "due_date": "2026-07-18",
                "subtotal": "100.00",
                "tax": "10.00",
                "total": "110.00",
                "currency": "USD",
                "correction_reason": "Matched the registered name shown on the invoice.",
            },
        )
        reviewer_workflow = self.client.get(
            f"/documents/{document_id}/workflow",
            headers=reviewer_headers,
        ).json()
        history = self.client.get(
            f"/review/{document_id}/corrections",
            headers=reviewer_headers,
        )
        uploader_history = self.client.get(
            f"/review/{document_id}/corrections",
            headers=uploader_headers,
        )

        self.assertEqual(requested.status_code, 200)
        self.assertEqual(uploader_workflow["current_stage"], "correction_requested")
        self.assertEqual(uploader_workflow["current_owner"], "Uploader")
        self.assertEqual(
            uploader_workflow["attention_reason"],
            "Use the full legal vendor name from the PDF.",
        )
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["correction_summary"]["latest_change_count"], 1)
        self.assertEqual(reviewer_workflow["current_stage"], "waiting_approval")
        self.assertEqual(reviewer_workflow["current_owner"], "Reviewer")
        self.assertIn(
            "correction_submitted",
            [event["event_type"] for event in reviewer_workflow["activity"]],
        )
        self.assertEqual(history.status_code, 200)
        event = history.json()["corrections"][0]
        self.assertEqual(event["actor"], "William Lo")
        self.assertEqual(event["reason_source"], "user")
        self.assertEqual(event["original_ai_data"]["vendor_name"], "Acme Logistics")
        self.assertEqual(event["changes"][0]["field_path"], "vendor_name")
        self.assertEqual(event["changes"][0]["before_value"], "Acme Logistics")
        self.assertEqual(event["changes"][0]["after_value"], "Acme Logistics Ltd")
        self.assertEqual(uploader_history.status_code, 403)

    def test_intake_draft_preserves_duplicate_validation_and_cannot_edit_approved_invoice(
        self,
    ) -> None:
        headers = {"X-Admin-Token": TOKEN, "X-User-Id": "William Lo"}
        document_ids: list[str] = []
        for filename in ("original.pdf", "copy.pdf"):
            upload = self.client.post(
                "/documents/upload",
                headers=headers,
                files={"file": (filename, PDF, "application/pdf")},
            )
            document_id = upload.json()["document"]["id"]
            self.client.post(f"/documents/{document_id}/process", headers=headers)
            document_ids.append(document_id)

        duplicate_payload = {
            "vendor_name": "Acme Logistics",
            "invoice_number": "INV-001",
            "invoice_date": "2026-06-18",
            "due_date": "2026-07-18",
            "subtotal": "100.00",
            "tax": "10.00",
            "total": "110.00",
            "currency": "USD",
        }
        saved = self.client.post(
            f"/invoices/{document_ids[1]}/draft",
            headers=headers,
            json=duplicate_payload,
        )
        approved = self.client.post(f"/review/{document_ids[0]}/approve", headers=headers)
        edit_after_approval = self.client.post(
            f"/invoices/{document_ids[0]}/draft",
            headers=headers,
            json={**duplicate_payload, "invoice_number": "CHANGED-AFTER-APPROVAL"},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            [issue["code"] for issue in saved.json()["extraction"]["validation"]],
            ["duplicate_invoice"],
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(edit_after_approval.status_code, 409)
        self.assertEqual(edit_after_approval.json()["detail"], "Finalized invoices cannot be edited.")

    def test_cancel_stops_queued_job_and_reprocess_creates_recovery_job(self) -> None:
        headers = {"X-Admin-Token": TOKEN, "X-User-Id": "William Lo"}
        upload = self.client.post(
            "/documents/upload",
            headers=headers,
            files={"file": ("cancel-me.pdf", PDF, "application/pdf")},
        )
        document_id = upload.json()["document"]["id"]
        original_job_id = upload.json()["job"]["id"]

        cancelled = self.client.post(f"/invoices/{document_id}/cancel", headers=headers)
        repeated_cancel = self.client.post(f"/invoices/{document_id}/cancel", headers=headers)
        reprocessed = self.client.post(f"/invoices/{document_id}/reprocess", headers=headers)
        workflow = self.client.get(f"/invoices/{document_id}/workflow", headers=headers).json()
        jobs = self.client.app.state.container.jobs.list_all()

        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["document"]["status"], "cancelled")
        self.assertEqual(repeated_cancel.status_code, 409)
        self.assertEqual(reprocessed.status_code, 200)
        self.assertEqual(reprocessed.json()["document"]["status"], "queued")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(str(jobs[0].id), original_job_id)
        self.assertEqual(jobs[0].status.value, "cancelled")
        self.assertEqual(jobs[1].status.value, "queued")
        self.assertIn(
            "intake cancelled by operator",
            [event["summary"] for event in workflow["activity"]],
        )


if __name__ == "__main__":
    unittest.main()
