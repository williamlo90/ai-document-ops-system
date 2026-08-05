import unittest

from app.evaluation.invoice import evaluate_invoice
from app.review.datasets import sample_invoice


class EvaluationTests(unittest.TestCase):
    def test_extraction_and_validation_are_reported_separately(self) -> None:
        result = evaluate_invoice(sample_invoice(), sample_invoice(total="111.00"))
        self.assertLess(result.field_match, 1.0)
        self.assertFalse(result.validation_match)
