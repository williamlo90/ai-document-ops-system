from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.documents.status import DocumentStatus


@dataclass
class DocumentRecord:
    original_filename: str
    storage_key: str
    content_type: str
    workspace_id: str = "default"
    submitted_by: str = "admin"
    size_bytes: int = 0
    id: UUID = field(default_factory=uuid4)
    status: DocumentStatus = DocumentStatus.UPLOADED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    document_id: UUID
    event_type: str
    actor: str
    old_status: DocumentStatus | None = None
    new_status: DocumentStatus | None = None
    payload_summary: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReviewTask:
    document_id: UUID
    status: str = "open"
    reviewer_notes: str | None = None
    assigned_to: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
