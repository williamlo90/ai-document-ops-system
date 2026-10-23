from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.documents.jobs import ProcessingJob
from app.providers.contracts import ProviderError


@dataclass(frozen=True)
class ProcessingRetryPolicy:
    max_attempts: int = 3
    base_seconds: int = 5
    max_seconds: int = 300

    def __post_init__(self) -> None:
        normalized_base = max(1, self.base_seconds)
        object.__setattr__(self, "base_seconds", normalized_base)
        object.__setattr__(self, "max_seconds", max(normalized_base, self.max_seconds))

    def error_code(self, error: Exception) -> str:
        if isinstance(error, ProviderError):
            return f"provider_error:{error.provider_name}"
        return error.__class__.__name__

    def should_retry(self, error: Exception, job: ProcessingJob) -> bool:
        return (
            isinstance(error, ProviderError)
            and error.retryable
            and job.attempt_count < self.max_attempts
        )

    def next_attempt_at(self, job: ProcessingJob) -> datetime:
        exponent = max(0, job.attempt_count - 1)
        bounded_delay = min(self.max_seconds, self.base_seconds * (2**exponent))
        jitter_percent = (job.id.int % 21) - 10
        jittered_delay = max(1.0, bounded_delay * (1 + jitter_percent / 100))
        return datetime.now(UTC) + timedelta(seconds=jittered_delay)
