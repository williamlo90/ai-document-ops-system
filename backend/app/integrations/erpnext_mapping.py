from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Any

from app.integrations.models import IntegrationInvoicePayload, IntegrationMappingError


ASSISTED_COMPANY = "Invoice Review Assisted Benchmark"
PAYABLE_ACCOUNTS = {
    "USD": "Creditors - IRA",
    "EUR": "Creditors EUR - IRA",
}
EXPENSE_ACCOUNT = "Professional Services - IRA"
ITEM_CODE = "BENCH-PROF-SVC"
ITEM_NAME = "Professional Services"
UOM = "Nos"
MONEY_QUANTUM = Decimal("0.01")

SUPPLIER_MAPPINGS: dict[str, str] = {
    "Acme Logistics": "Acme Logistics - Assisted Benchmark",
    "Faded Paper Services": "Faded Paper Services - Assisted Benchmark",
    "Keystone Manufacturing": "Keystone Manufacturing - Assisted Benchmark",
    "Meridian Consulting": "Meridian Consulting - Assisted Benchmark",
    "Northwind Freight": "Northwind Freight - Assisted Benchmark",
    "Rhein Handel GmbH": "Rhein Handel GmbH - Assisted Benchmark",
    "Sideways Shipping Co": "Sideways Shipping Co - Assisted Benchmark",
    "Summit Industrial Parts": "Summit Industrial Parts - Assisted Benchmark",
}
SUPPLIER_MAPPINGS_BY_KEY = {
    source_name.casefold(): supplier_name
    for source_name, supplier_name in SUPPLIER_MAPPINGS.items()
}

TAX_TEMPLATES: dict[Decimal, str | None] = {
    Decimal("0.00"): None,
    Decimal("10.00"): "Benchmark Input Tax 10% - IRA",
    Decimal("20.00"): "Benchmark Input Tax 20% - IRA",
}

FIXED_EUR_RATE_DATE = date(2026, 7, 3)


@dataclass(frozen=True)
class ERPNextMappedInvoice:
    request_core: dict[str, Any]
    source_total: Decimal

    @property
    def payload_hash(self) -> str:
        canonical = json.dumps(
            self.request_core,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def request(self, *, delivery_key: str, document_id: str) -> dict[str, Any]:
        return {
            **self.request_core,
            "custom_invoice_review_delivery_key": delivery_key,
            "custom_invoice_review_document_id": document_id,
            "custom_invoice_review_payload_hash": self.payload_hash,
        }


class ERPNextBenchmarkMapping:
    def __init__(self, *, today: Callable[[], date] | None = None) -> None:
        self._today = today or date.today

    def map_invoice(self, payload: IntegrationInvoicePayload) -> ERPNextMappedInvoice:
        vendor = _required_text(payload.vendor_name, "Vendor")
        supplier = SUPPLIER_MAPPINGS_BY_KEY.get(vendor.casefold())
        if supplier is None:
            raise IntegrationMappingError("Vendor has no configured ERPNext supplier mapping")

        invoice_number = _required_text(payload.invoice_number, "Invoice number")
        invoice_date = _required_date(payload.invoice_date, "Invoice date")
        due_date = _required_date(payload.due_date, "Due date")
        if due_date < invoice_date:
            raise IntegrationMappingError("Due date cannot be before invoice date")

        subtotal = _required_money(payload.subtotal, "Subtotal")
        tax = _required_money(payload.tax, "Tax")
        total = _required_money(payload.total, "Total")
        if subtotal <= 0 or tax < 0 or total <= 0:
            raise IntegrationMappingError(
                "Invoice amounts must be positive and tax cannot be negative"
            )
        if _money(subtotal + tax) != total:
            raise IntegrationMappingError("Subtotal and tax do not reconcile to total")

        currency = _required_text(payload.currency, "Currency").upper()
        conversion_rate = _conversion_rate(currency, invoice_date)
        payable_account = PAYABLE_ACCOUNTS.get(currency)
        if payable_account is None:
            raise IntegrationMappingError("Currency has no configured ERPNext payable account")

        tax_rate = _tax_rate(subtotal, tax)
        if tax_rate not in TAX_TEMPLATES:
            raise IntegrationMappingError("Tax rate has no configured ERPNext template")
        tax_template = TAX_TEMPLATES[tax_rate]
        items = _line_items(payload, subtotal, invoice_number)

        request: dict[str, Any] = {
            "doctype": "Purchase Invoice",
            "company": ASSISTED_COMPANY,
            "supplier": supplier,
            "posting_date": self._today().isoformat(),
            "set_posting_time": 1,
            "bill_no": invoice_number,
            "bill_date": invoice_date.isoformat(),
            "due_date": due_date.isoformat(),
            "currency": currency,
            "conversion_rate": float(conversion_rate),
            "credit_to": payable_account,
            "items": items,
            "docstatus": 0,
        }
        if tax_template is not None:
            request["taxes_and_charges"] = tax_template
            request["taxes"] = [_tax_row(tax_rate)]
        return ERPNextMappedInvoice(request_core=request, source_total=total)


def _line_items(
    payload: IntegrationInvoicePayload,
    subtotal: Decimal,
    invoice_number: str,
) -> list[dict[str, Any]]:
    if not payload.line_items:
        return [
            {
                "item_code": ITEM_CODE,
                "item_name": ITEM_NAME,
                "description": f"Invoice {invoice_number}"[:140],
                "qty": 1.0,
                "uom": UOM,
                "conversion_factor": 1.0,
                "rate": float(_money(subtotal)),
                "expense_account": EXPENSE_ACCOUNT,
            }
        ]

    rows: list[dict[str, Any]] = []
    line_total = Decimal("0")
    for index, item in enumerate(payload.line_items, start=1):
        description = _required_text(item.description, f"Line {index} description")
        quantity = _required_decimal(item.quantity, f"Line {index} quantity")
        unit_price = _required_decimal(item.unit_price, f"Line {index} unit price")
        amount = _required_money(item.amount, f"Line {index} amount")
        if quantity <= 0 or unit_price < 0 or amount < 0:
            raise IntegrationMappingError(f"Line {index} contains an invalid amount")
        if _money(quantity * unit_price) != amount:
            raise IntegrationMappingError(f"Line {index} quantity and rate do not reconcile")
        line_total += amount
        rows.append(
            {
                "item_code": ITEM_CODE,
                "item_name": ITEM_NAME,
                "description": description[:140],
                "qty": float(quantity),
                "uom": UOM,
                "conversion_factor": 1.0,
                "rate": float(_money(unit_price)),
                "expense_account": EXPENSE_ACCOUNT,
            }
        )
    if _money(line_total) != subtotal:
        raise IntegrationMappingError("Line items do not reconcile to subtotal")
    return rows


def _tax_rate(subtotal: Decimal, tax: Decimal) -> Decimal:
    if tax == 0:
        return Decimal("0.00")
    return ((tax / subtotal) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _conversion_rate(currency: str, invoice_date: date) -> Decimal:
    if currency == "USD":
        return Decimal("1.00")
    if currency == "EUR" and invoice_date == FIXED_EUR_RATE_DATE:
        return Decimal("1.10")
    raise IntegrationMappingError("Currency and invoice date have no configured ERPNext rate")


def _tax_row(rate: Decimal) -> dict[str, Any]:
    rate_text = _decimal_text(rate.quantize(Decimal("1")))
    return {
        "category": "Total",
        "add_deduct_tax": "Add",
        "charge_type": "On Net Total",
        "account_head": "Benchmark Input Tax - IRA",
        "description": f"Benchmark input tax {rate_text}%",
        "rate": float(rate),
    }


def _required_text(value: str | None, label: str) -> str:
    normalized = " ".join((value or "").split())
    if not normalized:
        raise IntegrationMappingError(f"{label} is required for ERPNext")
    return normalized


def _required_date(value: str | None, label: str) -> date:
    try:
        return date.fromisoformat(_required_text(value, label))
    except ValueError as exc:
        raise IntegrationMappingError(f"{label} must use YYYY-MM-DD") from exc


def _required_decimal(value: str | None, label: str) -> Decimal:
    try:
        result = Decimal(_required_text(value, label))
    except InvalidOperation as exc:
        raise IntegrationMappingError(f"{label} must be numeric") from exc
    if not result.is_finite():
        raise IntegrationMappingError(f"{label} must be finite")
    return result


def _required_money(value: str | None, label: str) -> Decimal:
    return _money(_required_decimal(value, label))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")
