from __future__ import annotations

import csv
from io import StringIO
from uuid import UUID

from app.extraction.schemas import InvoiceData


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralize_spreadsheet_formula(value: object | None) -> str:
    if value is None:
        return ""
    rendered = str(value)
    significant = rendered.lstrip(" \t\r\n")
    if significant.startswith(_FORMULA_PREFIXES):
        return f"'{rendered}"
    return rendered


def render_invoice_csv(document_id: UUID, invoice: InvoiceData) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "document_id",
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "due_date",
            "subtotal",
            "tax",
            "total",
            "currency",
        )
    )
    writer.writerow(
        tuple(
            neutralize_spreadsheet_formula(value)
            for value in (
                document_id,
                invoice.vendor_name,
                invoice.invoice_number,
                invoice.invoice_date,
                invoice.due_date,
                invoice.subtotal,
                invoice.tax,
                invoice.total,
                invoice.currency,
            )
        )
    )
    return output.getvalue().encode("utf-8")

