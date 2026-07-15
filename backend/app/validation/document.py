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
    for candidate in documents.list_by_workspace(document.workspace_id):
        if candidate.id == document.id:
            continue
        try:
            stored = extractions.get_for_document(candidate.id)
        except NotFoundError:
            continue
        candidate_data = stored.extraction_result.extraction.data
        if _invoice_identity(candidate_data.vendor_name, candidate_data.invoice_number) != identity:
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
