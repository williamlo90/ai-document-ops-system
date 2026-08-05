from __future__ import annotations

from app.extraction.schemas import InvoiceData
from app.validation.invoice import ValidationReport, validate_invoice


def validate_for_review(invoice: InvoiceData) -> ValidationReport:
    return validate_invoice(invoice)
