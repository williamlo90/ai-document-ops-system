from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


SCHEMA_VERSION = "invoice_v1"


@dataclass(frozen=True)
class InvoiceLineItem:
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


@dataclass(frozen=True)
class InvoiceData:
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: tuple[InvoiceLineItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FieldConfidence:
    field_name: str
    score: float | None
    source_page: int | None = None
    source_text: str | None = None


@dataclass(frozen=True)
class InvoiceExtraction:
    data: InvoiceData
    schema_version: str = SCHEMA_VERSION
    confidence: tuple[FieldConfidence, ...] = field(default_factory=tuple)
