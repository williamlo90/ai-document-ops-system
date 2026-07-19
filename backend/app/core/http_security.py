from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.settings import Settings, is_hosted


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if _is_document_content_path(request.url.path):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; base-uri 'self'; frame-ancestors 'self'",
            )
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'; "
                "frame-ancestors 'none'",
            )
            response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if _is_sensitive_response_path(request.url.path):
            response.headers.setdefault("Cache-Control", "no-store, private")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Expires", "0")
        return response


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, settings: Settings, cookie_name: str) -> None:
        super().__init__(app)
        self.enabled = is_hosted(settings)
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            self.enabled
            and request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}
            and request.cookies.get(self.cookie_name)
        ):
            source = request.headers.get("origin") or request.headers.get("referer")
            if not source or not _same_origin(source, str(request.base_url)):
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self.limit = max(1, requests)
        self.window = max(1, window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        now = monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return JSONResponse(
                    {"detail": "Rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": str(self.window)},
                )
            hits.append(now)
        return await call_next(request)


def _same_origin(source: str, target: str) -> bool:
    left, right = urlsplit(source), urlsplit(target)
    return (left.scheme, left.hostname, left.port) == (right.scheme, right.hostname, right.port)


def _is_document_content_path(path: str) -> bool:
    parts = [part for part in path.split("/") if part]
    return (
        len(parts) == 3
        and parts[0] == "documents"
        and parts[2] == "content"
        or len(parts) == 4
        and parts[0] == "ui"
        and parts[1] == "documents"
        and parts[3] == "preview"
    )


def _is_sensitive_response_path(path: str) -> bool:
    prefixes = (
        "/agent",
        "/agentops",
        "/auth",
        "/backoffice",
        "/documents",
        "/exports",
        "/integrations",
        "/internal",
        "/invoices",
        "/metrics",
        "/operations",
        "/providers",
        "/review",
    )
    return path.startswith(prefixes)
