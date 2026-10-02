from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcceptanceThresholds:
    availability_percent: float = 99.5
    unexpected_5xx_percent: float = 0.5
    read_p50_ms: float = 500.0
    read_p95_ms: float = 1_500.0
    read_p99_ms: float = 3_000.0
    upload_p50_ms: float = 1_500.0
    upload_p95_ms: float = 4_000.0
    upload_p99_ms: float = 8_000.0


@dataclass(frozen=True)
class RequestSample:
    operation: str
    started_at: str
    duration_ms: float
    status_code: int | None
    expected_statuses: tuple[int, ...]
    request_id: str
    trace_id: str
    document_id: str | None = None
    error: str | None = None

    @property
    def expected_response(self) -> bool:
        return self.error is None and self.status_code in self.expected_statuses


@dataclass(frozen=True)
class CheckResult:
    code: str
    passed: bool
    expected: str
    observed: str
    detail: str
