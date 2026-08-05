from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

_last_timestamp: datetime | None = None


def _monotonic_timestamp() -> datetime:
    global _last_timestamp
    current = datetime.now(UTC)
    if _last_timestamp is not None and current <= _last_timestamp:
        current = _last_timestamp + timedelta(microseconds=1)
    _last_timestamp = current
    return current


class ProcessingJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


@dataclass
class ProcessingJob:
    document_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: ProcessingJobStatus = ProcessingJobStatus.QUEUED
    attempt_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    provider_name: str | None = None
    provider_trace_id: str | None = None
    next_attempt_at: datetime | None = None
    lease_token: str | None = None
    created_at: datetime = field(default_factory=_monotonic_timestamp)
    updated_at: datetime = field(default_factory=_monotonic_timestamp)

    def start(self, *, lease_token: str | None = None) -> None:
        self.status = ProcessingJobStatus.RUNNING
        self.attempt_count += 1
        self.started_at = datetime.now(UTC)
        self.finished_at = None
        self.next_attempt_at = None
        self.lease_token = lease_token or uuid4().hex
        self.updated_at = self.started_at

    def succeed(self) -> None:
        self.status = ProcessingJobStatus.SUCCEEDED
        self.error_message = None
        self.finished_at = datetime.now(UTC)
        self.next_attempt_at = None
        self.lease_token = None
        self.updated_at = self.finished_at

    def fail(self, message: str) -> None:
        self.status = ProcessingJobStatus.FAILED
        self.error_message = message
        self.finished_at = datetime.now(UTC)
        self.next_attempt_at = None
        self.lease_token = None
        self.updated_at = self.finished_at

    def retry(self, message: str, *, next_attempt_at: datetime | None = None) -> None:
        self.status = ProcessingJobStatus.RETRYING
        self.error_message = message
        self.finished_at = None
        self.next_attempt_at = next_attempt_at
        self.lease_token = None
        self.updated_at = datetime.now(UTC)

    def dead_letter(self, message: str) -> None:
        self.status = ProcessingJobStatus.DEAD_LETTER
        self.error_message = message
        self.finished_at = datetime.now(UTC)
        self.next_attempt_at = None
        self.lease_token = None
        self.updated_at = self.finished_at

    def cancel(self) -> None:
        self.status = ProcessingJobStatus.CANCELLED
        self.error_message = None
        self.finished_at = datetime.now(UTC)
        self.next_attempt_at = None
        self.lease_token = None
        self.updated_at = self.finished_at
