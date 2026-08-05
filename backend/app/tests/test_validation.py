from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from app.extraction.schemas import InvoiceData, InvoiceLineItem
from app.validation.invoice import validate_invoice


class InvoiceValidationTests(unittest.TestCase):
    def test_valid_invoice_has_no_errors(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme Logistics",
            invoice_number="INV-001",
            invoice_date=date(2026, 6, 18),
            due_date=date(2026, 7, 18),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("110.00"),
            currency="USD",
            line_items=(InvoiceLineItem("Shipping", Decimal("2"), Decimal("50"), Decimal("100")),),
        )
        self.assertFalse(validate_invoice(invoice).has_errors)

    def test_missing_critical_fields_are_errors(self) -> None:
        report = validate_invoice(InvoiceData())
        self.assertEqual({issue.field_name for issue in report.issues}, {"vendor_name", "invoice_number", "invoice_date", "total"})

    def test_money_date_currency_and_line_item_rules(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-002",
            invoice_date=date(2026, 7, 18),
            due_date=date(2026, 6, 18),
            subtotal=Decimal("100"),
            tax=Decimal("10"),
            total=Decimal("110.02"),
            currency="BTC",
            line_items=(InvoiceLineItem("Item", Decimal("2"), Decimal("5"), Decimal("11")),),
        )
        self.assertEqual(
            {issue.code for issue in validate_invoice(invoice).issues},
            {"total_mismatch", "invalid_date_order", "unsupported_currency", "line_item_amount_mismatch"},
        )

    def test_money_difference_equal_to_tolerance_is_allowed(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-003",
            invoice_date=date(2026, 6, 18),
            subtotal=Decimal("100"),
            tax=Decimal("10"),
            total=Decimal("110.01"),
            currency="usd",
        )
        self.assertFalse(validate_invoice(invoice).has_errors)


if __name__ == "__main__":
    unittest.main()
