from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ExportBatchStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ExportBatchRecord:
    workspace_id: str
    document_ids: tuple[UUID, ...]
    destination: str
    export_format: str
    created_by: str
    status: ExportBatchStatus = ExportBatchStatus.DRAFT
    name: str | None = None
    last_run_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ExportRunRecord:
    workspace_id: str
    batch_id: UUID
    document_ids: tuple[UUID, ...]
    idempotency_key: str
    destination: str
    export_format: str
    actor: str
    status: ExportRunStatus = ExportRunStatus.RUNNING
    attempt_count: int = 1
    file_name: str | None = None
    artifact_content: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ExportBatchNotFound(LookupError):
    pass


class ExportRunNotFound(LookupError):
    pass


class ExportIdempotencyConflict(ValueError):
    pass


class ExportEligibilityError(ValueError):
    def __init__(self, message: str, checks: tuple[dict[str, object], ...]) -> None:
        super().__init__(message)
        self.checks = checks
