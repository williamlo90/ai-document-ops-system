from __future__ import annotations

from app.documents.models import DocumentRecord
from app.documents.repositories import DocumentRepository, ExtractionRepository, NotFoundError
from app.extraction.schemas import InvoiceData
from app.validation.invoice import (
    IssueSeverity,
    ValidationIssue,
    ValidationReport,
    validate_invoice,
)


def validate_document_invoice(
    invoice: InvoiceData,
    document: DocumentRecord,
    documents: DocumentRepository,
    extractions: ExtractionRepository,
) -> ValidationReport:
    report = validate_invoice(invoice)
    identity = _invoice_identity(invoice.vendor_name, invoice.invoice_number)
    if identity is None:
        return report
    for candidate_id in extractions.find_by_invoice_identity(*identity):
        if candidate_id == document.id:
            continue
        try:
            candidate = documents.get(candidate_id)
        except NotFoundError:
            continue
        if candidate.workspace_id != document.workspace_id:
            continue
        issue = ValidationIssue(
            field_name="invoice_number",
            severity=IssueSeverity.ERROR,
            code="duplicate_invoice",
            message="This vendor and invoice number already appear on another invoice.",
        )
        return ValidationReport(issues=(*report.issues, issue))
    return report


def _invoice_identity(
    vendor_name: str | None,
    invoice_number: str | None,
) -> tuple[str, str] | None:
    vendor = _identity_text(vendor_name)
    number = _identity_text(invoice_number)
    return (vendor, number) if vendor and number else None


def _identity_text(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())
