from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExportReceipt:
    export_id: UUID
    document_id: UUID
    storage_key: str
    idempotency_key: str


@runtime_checkable
class ApprovedInvoiceExporterPort(Protocol):
    def export_approved(
        self,
        document_id: UUID,
        *,
        actor: str,
        idempotency_key: str,
    ) -> ExportReceipt: ...
