from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.extraction.schemas import InvoiceData


MONEY_TOLERANCE = Decimal("0.01")
SUPPORTED_CURRENCIES = frozenset({"IDR", "USD", "EUR", "GBP", "SGD", "AUD", "JPY", "MYR"})
CRITICAL_FIELDS = ("vendor_name", "invoice_number", "invoice_date", "total")


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    field_name: str
    severity: IssueSeverity
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


def validate_invoice(invoice: InvoiceData) -> ValidationReport:
    issues = [
        *_validate_critical_fields(invoice),
        *_validate_totals(invoice),
        *_validate_dates(invoice),
        *_validate_currency(invoice),
        *_validate_line_items(invoice),
    ]
    return ValidationReport(issues=tuple(issues))


def _validate_critical_fields(invoice: InvoiceData) -> list[ValidationIssue]:
    return [
        ValidationIssue(field_name, IssueSeverity.ERROR, "missing_critical_field", f"{field_name} is required")
        for field_name in CRITICAL_FIELDS
        if getattr(invoice, field_name) in (None, "")
    ]


def _validate_totals(invoice: InvoiceData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if invoice.total is not None and invoice.total <= 0:
        issues.append(ValidationIssue("total", IssueSeverity.ERROR, "invalid_total", "total must be greater than 0"))
    if invoice.subtotal is not None and invoice.tax is not None and invoice.total is not None:
        if abs(invoice.subtotal + invoice.tax - invoice.total) > MONEY_TOLERANCE:
            issues.append(ValidationIssue("total", IssueSeverity.ERROR, "total_mismatch", "subtotal + tax must equal total within 0.01"))
    return issues


def _validate_dates(invoice: InvoiceData) -> list[ValidationIssue]:
    if invoice.invoice_date and invoice.due_date and invoice.invoice_date > invoice.due_date:
        return [ValidationIssue("due_date", IssueSeverity.ERROR, "invalid_date_order", "invoice_date must not be after due_date")]
    return []


def _validate_currency(invoice: InvoiceData) -> list[ValidationIssue]:
    if invoice.currency is not None and invoice.currency.upper() not in SUPPORTED_CURRENCIES:
        return [ValidationIssue("currency", IssueSeverity.ERROR, "unsupported_currency", "currency is not supported")]
    return []


def _validate_line_items(invoice: InvoiceData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, item in enumerate(invoice.line_items):
        if item.quantity is None or item.unit_price is None or item.amount is None:
            continue
        if abs(item.quantity * item.unit_price - item.amount) > MONEY_TOLERANCE:
            issues.append(ValidationIssue(f"line_items[{index}].amount", IssueSeverity.ERROR, "line_item_amount_mismatch", "quantity * unit_price must equal amount within 0.01"))
    return issues
