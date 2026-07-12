from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe
from threading import Lock
from time import time
from hmac import compare_digest

from app.core.settings import Settings, is_production_like, is_public_demo


class UnauthorizedError(PermissionError):
    pass


class SecurityConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class SecurityContext:
    actor: str
    is_admin: bool = False
    workspace_id: str = "default"
    user_id: str = "admin"
    role: str = "admin"


INTAKE_ROLES = {"intake", "operator", "uploader"}
REVIEW_ROLES = {"reviewer"}


class SessionStore:
    """Process-local opaque sessions; credentials never leave the server after login."""

    def __init__(self, ttl_seconds: int = 28_800) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, tuple[SecurityContext, float]] = {}
        self._lock = Lock()

    def create(self, context: SecurityContext) -> str:
        session_id = token_urlsafe(32)
        with self._lock:
            self._sessions[session_id] = (context, time() + self.ttl_seconds)
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


def validate_admin_token_policy(settings: Settings) -> None:
    if not is_production_like(settings):
        return
    token = settings.admin_token or ""
    weak_tokens = {"", "admin", "password", "test-token", "changeme", "change-me"}
    if token.strip().lower() in weak_tokens or len(token) < 24:
        raise SecurityConfigurationError(
            "Production requires APP_ADMIN_TOKEN with at least 24 non-default characters"
        )


def validate_public_demo_provider_policy(settings: Settings) -> None:
    if not is_public_demo(settings):
        return
    providers = {
        "PARSER_PROVIDER": settings.parser_provider.strip().lower(),
        "EXTRACTOR_PROVIDER": settings.extractor_provider.strip().lower(),
    }
    non_mock = {key: value for key, value in providers.items() if value != "mock"}
    if non_mock:
        raise SecurityConfigurationError(
            "Public demo mode must use mock parser/extractor providers"
        )


def verify_admin_token(
    provided_token: str | None,
    expected_token: str | None,
    workspace_id: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
) -> SecurityContext:
    if not expected_token:
        raise UnauthorizedError("Admin token is not configured")
    if not provided_token or not compare_digest(provided_token, expected_token):
        raise UnauthorizedError("Invalid admin token")
    normalized_role = (role or "admin").strip().lower() or "admin"
    normalized_user = (user_id or normalized_role).strip() or normalized_role
    return SecurityContext(
        actor=normalized_user,
        is_admin=normalized_role == "admin",
        workspace_id=(workspace_id or "default").strip() or "default",
        user_id=normalized_user,
        role=normalized_role,
    )


def require_admin(context: SecurityContext) -> None:
    if not context.is_admin:
        raise UnauthorizedError("Admin access required")


def require_any_role(context: SecurityContext, allowed_roles: set[str]) -> None:
    if context.role == "admin" and not context.is_admin:
        raise UnauthorizedError("Admin role requires admin access")
    if context.role not in allowed_roles:
        raise UnauthorizedError("Required role not present")


def is_intake_role(context: SecurityContext) -> bool:
    return not context.is_admin and context.role in INTAKE_ROLES
