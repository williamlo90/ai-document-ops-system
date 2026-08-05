from __future__ import annotations

import unittest

from app.documents.status import DocumentStatus, InvalidStatusTransition, require_transition


class DocumentStatusTests(unittest.TestCase):
    def test_allowed_happy_path_transitions(self) -> None:
        path = [
            DocumentStatus.UPLOADED,
            DocumentStatus.QUEUED,
            DocumentStatus.PROCESSING,
            DocumentStatus.EXTRACTED,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.APPROVED,
            DocumentStatus.EXPORTED,
        ]
        for current, target in zip(path, path[1:], strict=False):
            require_transition(current, target)

    def test_forbids_direct_upload_to_approved(self) -> None:
        with self.assertRaises(InvalidStatusTransition):
            require_transition(DocumentStatus.UPLOADED, DocumentStatus.APPROVED)

    def test_forbids_failed_to_approved(self) -> None:
        with self.assertRaises(InvalidStatusTransition):
            require_transition(DocumentStatus.FAILED, DocumentStatus.APPROVED)

    def test_allows_processing_back_to_queued_for_retry(self) -> None:
        require_transition(DocumentStatus.PROCESSING, DocumentStatus.QUEUED)

    def test_forbids_exported_to_needs_review(self) -> None:
        with self.assertRaises(InvalidStatusTransition):
            require_transition(DocumentStatus.EXPORTED, DocumentStatus.NEEDS_REVIEW)

    def test_rejected_is_terminal(self) -> None:
        with self.assertRaises(InvalidStatusTransition):
            require_transition(DocumentStatus.REJECTED, DocumentStatus.APPROVED)


if __name__ == "__main__":
    unittest.main()
