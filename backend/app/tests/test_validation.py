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

        report = validate_invoice(invoice)

        self.assertFalse(report.has_errors)
        self.assertEqual(report.issues, ())

    def test_missing_critical_fields_are_errors(self) -> None:
        report = validate_invoice(InvoiceData())

        self.assertTrue(report.has_errors)
        self.assertEqual(
            {issue.field_name for issue in report.issues},
            {"vendor_name", "invoice_number", "invoice_date", "total"},
        )

    def test_total_mismatch_uses_money_tolerance(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-002",
            invoice_date=date(2026, 6, 18),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("110.02"),
            currency="USD",
        )

        report = validate_invoice(invoice)

        self.assertIn("total_mismatch", {issue.code for issue in report.issues})

    def test_total_difference_equal_to_tolerance_is_allowed(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-002A",
            invoice_date=date(2026, 6, 18),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("110.01"),
            currency="usd",
        )

        report = validate_invoice(invoice)

        self.assertFalse(report.has_errors)

    def test_invalid_date_order_is_error(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-003",
            invoice_date=date(2026, 7, 18),
            due_date=date(2026, 6, 18),
            total=Decimal("10"),
        )

        report = validate_invoice(invoice)

        self.assertIn("invalid_date_order", {issue.code for issue in report.issues})

    def test_unsupported_currency_is_error(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-004",
            invoice_date=date(2026, 6, 18),
            total=Decimal("10"),
            currency="BTC",
        )

        report = validate_invoice(invoice)

        self.assertIn("unsupported_currency", {issue.code for issue in report.issues})

    def test_line_item_amount_mismatch_is_error(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-005",
            invoice_date=date(2026, 6, 18),
            total=Decimal("10"),
            line_items=(InvoiceLineItem("Item", Decimal("2"), Decimal("5"), Decimal("11")),),
        )

        report = validate_invoice(invoice)

        self.assertIn("line_item_amount_mismatch", {issue.code for issue in report.issues})

    def test_total_must_be_greater_than_zero(self) -> None:
        invoice = InvoiceData(
            vendor_name="Acme",
            invoice_number="INV-006",
            invoice_date=date(2026, 6, 18),
            total=Decimal("0"),
        )

        report = validate_invoice(invoice)

        self.assertIn("invalid_total", {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
