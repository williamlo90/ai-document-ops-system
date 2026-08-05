from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest
from secrets import token_urlsafe
from threading import Lock
from time import time

from app.core.settings import Settings


class UnauthorizedError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class SecurityContext:
    actor: str
    user_id: str
    role: str
    workspace_id: str
    is_admin: bool = False


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, tuple[SecurityContext, float]] = {}
        self._lock = Lock()

    def create(self, context: SecurityContext) -> str:
        session_id = token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = (context, time() + self._ttl_seconds)
        return session_id

    def get(self, session_id: str | None) -> SecurityContext | None:
        if not session_id:
            return None
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            context, expires_at = entry
            if expires_at <= time():
                self._sessions.pop(session_id, None)
                return None
            return context

    def revoke(self, session_id: str | None) -> None:
        if session_id:
            with self._lock:
                self._sessions.pop(session_id, None)


def authenticate_access_token(token: str | None, settings: Settings) -> SecurityContext:
    principals = (
        (settings.admin_token, "Administrator", "admin", "admin", True),
        (settings.uploader_token, "Invoice Uploader", "uploader", "uploader", False),
        (settings.reviewer_token, "Invoice Reviewer", "reviewer", "reviewer", False),
    )
    for expected, actor, user_id, role, is_admin in principals:
        if token and expected and compare_digest(token, expected):
            return SecurityContext(actor, user_id, role, settings.workspace_id, is_admin)
    raise UnauthorizedError("Invalid access token")


def require_role(context: SecurityContext, *roles: str) -> None:
    if context.role not in roles:
        raise UnauthorizedError("Required role not present")
