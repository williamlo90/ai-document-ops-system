from __future__ import annotations

import unittest

from app.documents.status import (
    DocumentStatus,
    IntakeDraftLocked,
    InvalidStatusTransition,
    require_intake_editable,
    require_transition,
)


class DocumentStatusTests(unittest.TestCase):
    def test_allowed_review_path(self) -> None:
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

    def test_forbids_status_shortcuts(self) -> None:
        for current in (DocumentStatus.UPLOADED, DocumentStatus.FAILED):
            with self.subTest(current=current), self.assertRaises(InvalidStatusTransition):
                require_transition(current, DocumentStatus.APPROVED)

    def test_terminal_states_are_not_intake_editable(self) -> None:
        for status in (DocumentStatus.APPROVED, DocumentStatus.REJECTED, DocumentStatus.EXPORTED):
            with self.subTest(status=status), self.assertRaises(IntakeDraftLocked):
                require_intake_editable(status)


if __name__ == "__main__":
    unittest.main()
