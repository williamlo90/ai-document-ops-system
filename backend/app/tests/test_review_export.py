from __future__ import annotations

import unittest
from decimal import Decimal

from app.bootstrap.container import build_container
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.review.datasets import sample_invoice
from app.review.services import ApprovalBlocked


class ReviewDecisionTests(unittest.TestCase):
    def test_blocking_issue_prevents_approval_then_correction_allows_human_decision(self) -> None:
        container = build_container(Settings())
        document = DocumentRecord("invoice.pdf", "key", "application/pdf", status=DocumentStatus.NEEDS_REVIEW)
        with container.persistence.transactions.transaction():
            container.persistence.documents.add(document)
        container.review_module.service.seed(document.id, sample_invoice(total="111.00"))
        with self.assertRaises(ApprovalBlocked):
            container.review_module.service.decide(document.id, approve=True, actor="Reviewer", note="approve")
        container.review_module.service.correct(document.id, field_name="total", value="110.00", actor="Reviewer", reason="Matched PDF")
        event = container.review_module.service.decide(document.id, approve=True, actor="Reviewer", note="Verified")
        self.assertEqual(event.new_status, DocumentStatus.APPROVED)
        self.assertEqual(container.persistence.documents.get(document.id).status, DocumentStatus.APPROVED)  # type: ignore[union-attr]
        self.assertEqual(container.persistence.reviews.get(document.id).original.total, Decimal("111.00"))  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
