from __future__ import annotations

from dataclasses import dataclass

from app.extraction.schemas import InvoiceData
from app.validation.document import validate_for_review


FIELDS = ("vendor_name", "invoice_number", "invoice_date", "due_date", "subtotal", "tax", "total", "currency")


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    field_match: float
    validation_match: bool


def evaluate_invoice(expected: InvoiceData, actual: InvoiceData) -> EvaluationResult:
    matched = sum(getattr(expected, field) == getattr(actual, field) for field in FIELDS)
    expected_codes = {issue.code for issue in validate_for_review(expected).issues}
    actual_codes = {issue.code for issue in validate_for_review(actual).issues}
    return EvaluationResult(matched / len(FIELDS), expected_codes == actual_codes)
