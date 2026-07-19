from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


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


class IntegrationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntegrationDeliveryRecord:
    workspace_id: str
    document_id: UUID
    adapter_name: str
    idempotency_key: str
    payload_hash: str
    status: IntegrationDeliveryStatus = IntegrationDeliveryStatus.PENDING
    external_id: str | None = None
    error_code: str | None = None
    retryable: bool = False
    attempt_count: int = 1
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class IntegrationDeliveryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class IntegrationIdempotencyConflict(ValueError):
    pass


class IntegrationOutcomeUnknown(RuntimeError):
    pass


class AccountingIntegrationAdapter(Protocol):
    name: str

    def send_invoice(
        self,
        payload: IntegrationInvoicePayload,
        *,
        idempotency_key: str,
    ) -> IntegrationExportResult: ...
