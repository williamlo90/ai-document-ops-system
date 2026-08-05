from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.extraction.schemas import InvoiceData


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    document_id: UUID
    original: InvoiceData
    current: InvoiceData


@dataclass(frozen=True, slots=True)
class CorrectionEvent:
    document_id: UUID
    field_name: str
    before: str | None
    after: str | None
    actor: str
    reason: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
