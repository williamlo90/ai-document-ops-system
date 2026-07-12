from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


LOGGER_NAME = "docintel.operations"
HTTP_LOGGER_NAME = "docintel.http"


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for container stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "trace_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_structured_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_docintel_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler._docintel_json = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


class HttpMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = {}
        self._duration_seconds: dict[tuple[str, str], float] = {}

    def observe(self, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            request_key = (method, route, status_code)
            duration_key = (method, route)
            self._requests[request_key] = self._requests.get(request_key, 0) + 1
            self._duration_seconds[duration_key] = (
                self._duration_seconds.get(duration_key, 0.0) + duration_seconds
            )

    def prometheus(self) -> str:
        lines = [
            "# HELP docintel_http_requests_total HTTP requests handled.",
            "# TYPE docintel_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), value in sorted(self._requests.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f"docintel_http_requests_total{{{labels}}} {value}")
            lines.extend(
                [
                    "# HELP docintel_http_request_duration_seconds_sum Total request duration.",
                    "# TYPE docintel_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, route), value in sorted(self._duration_seconds.items()):
                labels = f'method="{method}",route="{route}"'
                lines.append(f"docintel_http_request_duration_seconds_sum{{{labels}}} {value:.6f}")
        return "\n".join(lines) + "\n"


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, metrics: HttpMetrics) -> None:
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        trace_id = _trace_id(request.headers.get("traceparent")) or uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            duration = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", request.url.path)
            self.metrics.observe(request.method, route, status_code, duration)
            logging.getLogger(HTTP_LOGGER_NAME).info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": route,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 3),
                },
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        return response


def _trace_id(traceparent: str | None) -> str | None:
    if not traceparent:
        return None
    parts = traceparent.split("-")
    if len(parts) == 4 and len(parts[1]) == 32:
        try:
            int(parts[1], 16)
        except ValueError:
            return None
        return parts[1].lower()
    return None


@dataclass(frozen=True)
class OperationEvent:
    event_type: str
    workspace_id: str
    actor: str
    document_id: str | None = None
    job_id: str | None = None
    provider_name: str | None = None
    status: str | None = None
    error_code: str | None = None
    retryable: bool | None = None
    attempt_count: int | None = None
    created_at: str = ""


def log_operation(event: OperationEvent) -> None:
    payload = asdict(event)
    payload["created_at"] = event.created_at or datetime.now(UTC).isoformat()
    clean_payload = {key: value for key, value in payload.items() if value is not None}
    logging.getLogger(LOGGER_NAME).info(json.dumps(clean_payload, sort_keys=True))


def readiness_payload(*, database_ready: bool, storage_ready: bool) -> dict[str, Any]:
    status = "ready" if database_ready and storage_ready else "not_ready"
    return {
        "status": status,
        "checks": {
            "database": "ok" if database_ready else "failed",
            "storage": "ok" if storage_ready else "failed",
        },
    }
