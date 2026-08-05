from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.http_headers import NO_STORE_HEADERS
from app.core.settings import Settings, is_hosted


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/documents/") and request.url.path.endswith("/content"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self'")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        else:
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
            response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith(("/auth", "/workspace", "/internal")):
            for name, value in NO_STORE_HEADERS.items():
                response.headers.setdefault(name, value)
        return response


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings, cookie_name: str) -> None:
        super().__init__(app)
        self.enabled = is_hosted(settings)
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.enabled and request.method not in {"GET", "HEAD", "OPTIONS"} and request.cookies.get(self.cookie_name):
            source = request.headers.get("origin") or request.headers.get("referer")
            if not source or not _same_origin(source, str(request.base_url)):
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, requests: int, window_seconds: int) -> None:
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
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": str(self.window)})
            hits.append(now)
        return await call_next(request)


def _same_origin(source: str, target: str) -> bool:
    left, right = urlsplit(source), urlsplit(target)
    return (left.scheme, left.hostname, left.port) == (right.scheme, right.hostname, right.port)
