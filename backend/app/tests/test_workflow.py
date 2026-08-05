from __future__ import annotations

import unittest

from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus, IntakeDraftLocked, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService


class DocumentWorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = DocumentRecord("invoice.pdf", "storage-key.pdf", "application/pdf")
        self.workflow = DocumentWorkflowService()

    def test_transition_updates_document_and_records_actor(self) -> None:
        event = self.workflow.transition(self.document, DocumentStatus.QUEUED, actor="tester")
        self.assertEqual(self.document.status, DocumentStatus.QUEUED)
        self.assertEqual((event.old_status, event.new_status), (DocumentStatus.UPLOADED, DocumentStatus.QUEUED))
        self.assertEqual(event.actor, "tester")

    def test_forbidden_transition_does_not_mutate_document(self) -> None:
        with self.assertRaises(InvalidStatusTransition):
            self.workflow.transition(self.document, DocumentStatus.APPROVED, actor="tester")
        self.assertEqual(self.document.status, DocumentStatus.UPLOADED)

    def test_confidence_data_has_no_transition_entry_point(self) -> None:
        self.assertNotIn("confidence", DocumentWorkflowService.transition.__annotations__)
        with self.assertRaises(InvalidStatusTransition):
            self.workflow.transition(self.document, DocumentStatus.APPROVED, actor="model")

    def test_final_state_cannot_save_intake_draft(self) -> None:
        self.document.status = DocumentStatus.APPROVED
        with self.assertRaises(IntakeDraftLocked):
            self.workflow.save_intake_draft(self.document, actor="operator")


if __name__ == "__main__":
    unittest.main()
