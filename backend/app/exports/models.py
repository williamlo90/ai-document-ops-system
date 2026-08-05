from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class ExportRecord:
    document_id: UUID
    workspace_id: str
    idempotency_key: str
    requested_by: str
    filename: str
    content: bytes
    content_sha256: str
    id: UUID = field(default_factory=uuid4)
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

