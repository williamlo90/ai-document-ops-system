from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extraction.schemas import InvoiceData


def sample_invoice(*, total: str = "110.00") -> InvoiceData:
    return InvoiceData(
        vendor_name="Acme Logistics",
        invoice_number="INV-001",
        invoice_date=date(2026, 6, 18),
        due_date=date(2026, 7, 18),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal(total),
        currency="USD",
    )
