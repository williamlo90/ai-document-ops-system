from __future__ import annotations

import unittest

from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService


class DocumentWorkflowServiceTests(unittest.TestCase):
    def test_transition_updates_document_and_creates_audit_event(self) -> None:
        document = DocumentRecord("invoice.pdf", "storage-key.pdf", "application/pdf")
        workflow = DocumentWorkflowService()

        event = workflow.transition(document, DocumentStatus.QUEUED, actor="tester")

        self.assertEqual(document.status, DocumentStatus.QUEUED)
        self.assertEqual(event.old_status, DocumentStatus.UPLOADED)
        self.assertEqual(event.new_status, DocumentStatus.QUEUED)
        self.assertEqual(event.actor, "tester")

    def test_forbidden_transition_does_not_create_audit_event(self) -> None:
        document = DocumentRecord("invoice.pdf", "storage-key.pdf", "application/pdf")
        workflow = DocumentWorkflowService()

        with self.assertRaises(InvalidStatusTransition):
            workflow.transition(document, DocumentStatus.APPROVED, actor="tester")

        self.assertEqual(document.status, DocumentStatus.UPLOADED)

    def test_full_review_path_creates_ordered_events(self) -> None:
        document = DocumentRecord("invoice.pdf", "storage-key.pdf", "application/pdf")
        workflow = DocumentWorkflowService()

        events = []
        for target in (
            DocumentStatus.QUEUED,
            DocumentStatus.PROCESSING,
            DocumentStatus.EXTRACTED,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.APPROVED,
            DocumentStatus.EXPORTED,
        ):
            events.append(workflow.transition(document, target, actor="tester"))

        self.assertEqual(document.status, DocumentStatus.EXPORTED)
        self.assertEqual(
            [event.event_type for event in events],
            [
                "processing_queued",
                "processing_started",
                "processing_finished",
                "review_required",
                "document_approved",
                "document_exported",
            ],
        )

    def test_review_reject_path_creates_rejected_event(self) -> None:
        document = DocumentRecord("invoice.pdf", "storage-key.pdf", "application/pdf")
        workflow = DocumentWorkflowService()

        for target in (
            DocumentStatus.QUEUED,
            DocumentStatus.PROCESSING,
            DocumentStatus.EXTRACTED,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.REJECTED,
        ):
            event = workflow.transition(document, target, actor="tester")

        self.assertEqual(document.status, DocumentStatus.REJECTED)
        self.assertEqual(event.event_type, "document_rejected")


if __name__ == "__main__":
    unittest.main()
