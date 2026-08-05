from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.extraction.schemas import InvoiceData


MONEY_TOLERANCE = Decimal("0.01")
SUPPORTED_CURRENCIES = {"IDR", "USD", "EUR", "GBP", "SGD", "AUD", "JPY", "MYR"}
CRITICAL_FIELDS = ("vendor_name", "invoice_number", "invoice_date", "total")


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    field_name: str
    severity: IssueSeverity
    code: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


def validate_invoice(invoice: InvoiceData) -> ValidationReport:
    issues: list[ValidationIssue] = []
    issues.extend(_validate_critical_fields(invoice))
    issues.extend(_validate_totals(invoice))
    issues.extend(_validate_dates(invoice))
    issues.extend(_validate_currency(invoice))
    issues.extend(_validate_line_items(invoice))
    return ValidationReport(issues=tuple(issues))


def _validate_critical_fields(invoice: InvoiceData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for field_name in CRITICAL_FIELDS:
        if getattr(invoice, field_name) in (None, ""):
            issues.append(
                ValidationIssue(
                    field_name=field_name,
                    severity=IssueSeverity.ERROR,
                    code="missing_critical_field",
                    message=f"{field_name} is required",
                )
            )
    return issues


def _validate_totals(invoice: InvoiceData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if invoice.total is not None and invoice.total <= 0:
        issues.append(
            ValidationIssue(
                field_name="total",
                severity=IssueSeverity.ERROR,
                code="invalid_total",
                message="total must be greater than 0",
            )
        )
    if invoice.subtotal is not None and invoice.tax is not None and invoice.total is not None:
        expected = invoice.subtotal + invoice.tax
        if abs(expected - invoice.total) > MONEY_TOLERANCE:
            issues.append(
                ValidationIssue(
                    field_name="total",
                    severity=IssueSeverity.ERROR,
                    code="total_mismatch",
                    message="subtotal + tax must equal total within 0.01",
                )
            )
    return issues


def _validate_dates(invoice: InvoiceData) -> list[ValidationIssue]:
    if invoice.invoice_date and invoice.due_date and invoice.invoice_date > invoice.due_date:
        return [
            ValidationIssue(
                field_name="due_date",
                severity=IssueSeverity.ERROR,
                code="invalid_date_order",
                message="invoice_date must not be after due_date",
            )
        ]
    return []


def _validate_currency(invoice: InvoiceData) -> list[ValidationIssue]:
    if invoice.currency is None:
        return []
    if invoice.currency.upper() not in SUPPORTED_CURRENCIES:
        return [
            ValidationIssue(
                field_name="currency",
                severity=IssueSeverity.ERROR,
                code="unsupported_currency",
                message="currency is not supported",
            )
        ]
    return []


def _validate_line_items(invoice: InvoiceData) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, item in enumerate(invoice.line_items):
        if item.quantity is None or item.unit_price is None or item.amount is None:
            continue
        expected = item.quantity * item.unit_price
        if abs(expected - item.amount) > MONEY_TOLERANCE:
            issues.append(
                ValidationIssue(
                    field_name=f"line_items[{index}].amount",
                    severity=IssueSeverity.ERROR,
                    code="line_item_amount_mismatch",
                    message="quantity * unit_price must equal amount within 0.01",
                )
            )
    return issues
