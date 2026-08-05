from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from secrets import token_urlsafe
from uuid import UUID, uuid4


class JobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRY = "retry"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StaleLeaseError(RuntimeError):
    pass


@dataclass(slots=True)
class ProcessingJob:
    document_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.QUEUED
    attempt_count: int = 0
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    next_attempt_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    error_code: str | None = None

    def claim(self, lease_seconds: int, now: datetime | None = None) -> str:
        current = now or datetime.now(UTC)
        if self.status not in {JobStatus.QUEUED, JobStatus.RETRY} or self.next_attempt_at > current:
            raise StaleLeaseError("Job is not claimable")
        self.status = JobStatus.PROCESSING
        self.attempt_count += 1
        self.lease_token = token_urlsafe(24)
        self.lease_expires_at = current + timedelta(seconds=lease_seconds)
        return self.lease_token

    def require_lease(self, token: str) -> None:
        if self.status != JobStatus.PROCESSING or self.lease_token != token:
            raise StaleLeaseError("Worker lease is stale")

    def heartbeat(self, token: str, lease_seconds: int) -> None:
        self.require_lease(token)
        self.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)

    def complete(self, token: str) -> None:
        self.require_lease(token)
        self.status = JobStatus.COMPLETED
        self.lease_token = None
        self.lease_expires_at = None

    def fail(self, token: str, *, retryable: bool, error_code: str) -> None:
        self.require_lease(token)
        self.status = JobStatus.RETRY if retryable else JobStatus.FAILED
        self.error_code = error_code
        self.lease_token = None
        self.lease_expires_at = None

    def reclaim_if_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        if self.status == JobStatus.PROCESSING and self.lease_expires_at and self.lease_expires_at <= current:
            self.status = JobStatus.RETRY
            self.lease_token = None
            self.lease_expires_at = None
            return True
        return False
