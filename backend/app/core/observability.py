from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(slots=True)
class RequestMetrics:
    requests: int = 0
    failures: int = 0
    total_duration_seconds: float = 0.0

    def record(self, *, status_code: int, duration_seconds: float) -> None:
        self.requests += 1
        self.failures += int(status_code >= 500)
        self.total_duration_seconds += duration_seconds


class RequestObservabilityMiddleware:
    """Attach a correlation identifier and record bounded in-process request metrics."""

    def __init__(self, app: ASGIApp, metrics: RequestMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get("x-request-id", "").strip() or uuid4().hex
        started = perf_counter()
        status_code = 500

        async def send_with_observability(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii", errors="ignore")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_observability)
        finally:
            self.metrics.record(
                status_code=status_code,
                duration_seconds=perf_counter() - started,
            )


def readiness_payload(*, lifecycle_ready: bool, database_ready: bool, storage_ready: bool) -> dict[str, object]:
    checks = {
        "lifecycle": "ready" if lifecycle_ready else "stopping",
        "database": "ready" if database_ready else "unavailable",
        "storage": "ready" if storage_ready else "unavailable",
    }
    ready = lifecycle_ready and database_ready and storage_ready
    return {"status": "ready" if ready else "not_ready", "checks": checks}


def request_metrics_payload(metrics: RequestMetrics) -> dict[str, int | float]:
    return {
        "requests": metrics.requests,
        "failures": metrics.failures,
        "total_duration_seconds": round(metrics.total_duration_seconds, 6),
    }
