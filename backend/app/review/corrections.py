from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from app.extraction.schemas import InvoiceData


EDITABLE_FIELDS = frozenset({"vendor_name", "invoice_number", "invoice_date", "due_date", "subtotal", "tax", "total", "currency"})


def apply_correction(invoice: InvoiceData, field_name: str, value: str | None) -> InvoiceData:
    if field_name not in EDITABLE_FIELDS:
        raise ValueError("Field is not editable")
    if field_name == "vendor_name":
        return replace(invoice, vendor_name=value)
    if field_name == "invoice_number":
        return replace(invoice, invoice_number=value)
    if field_name == "invoice_date":
        return replace(invoice, invoice_date=date.fromisoformat(value) if value else None)
    if field_name == "due_date":
        return replace(invoice, due_date=date.fromisoformat(value) if value else None)
    if field_name == "subtotal":
        return replace(invoice, subtotal=Decimal(value) if value else None)
    if field_name == "tax":
        return replace(invoice, tax=Decimal(value) if value else None)
    if field_name == "total":
        return replace(invoice, total=Decimal(value) if value else None)
    return replace(invoice, currency=value)
