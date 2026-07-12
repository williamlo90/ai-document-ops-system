from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class IntegrationLineItem:
    description: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    amount: str | None = None


@dataclass(frozen=True)
class IntegrationInvoicePayload:
    document_id: str
    workspace_id: str
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    subtotal: str | None
    tax: str | None
    total: str | None
    currency: str | None
    line_items: tuple[IntegrationLineItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntegrationExportResult:
    adapter_name: str
    external_id: str
    status: str = "sent"
    retryable: bool = False


class IntegrationDeliveryError(RuntimeError):
    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class AccountingIntegrationAdapter(Protocol):
    name: str

    def send_invoice(self, payload: IntegrationInvoicePayload) -> IntegrationExportResult: ...
