import unittest
from uuid import uuid4

from app.agent.repositories import AgentRunRepository
from app.agent.service import ReadOnlyCopilotService
from app.agent.tools import ReadOnlyInvoiceTools
from app.review.datasets import sample_invoice
from app.review.models import ReviewRecord
from app.review.repositories import InMemoryReviewRepository


class AgentCopilotTests(unittest.TestCase):
    def test_answer_is_grounded_and_run_is_recorded(self) -> None:
        document_id = uuid4()
        reviews = InMemoryReviewRepository()
        invoice = sample_invoice()
        reviews.save(ReviewRecord(document_id, invoice, invoice))
        runs = AgentRunRepository()
        answer = ReadOnlyCopilotService(ReadOnlyInvoiceTools(reviews), runs).answer(document_id, "What is the total?")
        self.assertFalse(answer.abstained)
        self.assertEqual(answer.citations[0].field_name, "total")
        self.assertEqual(len(runs.list_for_document(document_id)), 1)
