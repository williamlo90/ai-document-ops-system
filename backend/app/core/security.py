from __future__ import annotations

from dataclasses import dataclass
from secrets import token_urlsafe
from threading import Lock
from time import time
from hmac import compare_digest

from app.core.settings import Settings, is_hosted, is_public_demo


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


def validate_access_token_policy(settings: Settings) -> None:
    credentials = {
        "APP_ADMIN_TOKEN": settings.admin_token,
        "APP_UPLOADER_TOKEN": settings.uploader_token,
        "APP_REVIEWER_TOKEN": settings.reviewer_token,
    }
    configured = {name: value for name, value in credentials.items() if value}
    if len(set(configured.values())) != len(configured):
        raise SecurityConfigurationError("Access tokens must be unique per server-owned role")
    if not is_hosted(settings):
        return

    required = {"APP_ADMIN_TOKEN"}
    if is_public_demo(settings):
        required.update({"APP_UPLOADER_TOKEN", "APP_REVIEWER_TOKEN"})
    missing = sorted(name for name in required if not credentials[name])
    if missing:
        raise SecurityConfigurationError(
            f"Hosted mode requires configured credentials: {', '.join(missing)}"
        )

    weak_tokens = {
        "",
        "123",
        "admin",
        "password",
        "test-token",
        "changeme",
        "change-me",
    }
    weak = sorted(
        name
        for name, value in configured.items()
        if value.strip().lower() in weak_tokens or len(value) < 24
    )
    if weak:
        raise SecurityConfigurationError(
            f"Hosted mode requires at least 24 non-default characters for: {', '.join(weak)}"
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


def authenticate_access_token(
    provided_token: str | None,
    settings: Settings,
) -> SecurityContext:
    if not provided_token:
        raise UnauthorizedError("Access token is required")
    workspace_id = settings.workspace_id.strip() or "default"
    principals = (
        (
            settings.admin_token,
            SecurityContext(
                actor="Administrator",
                is_admin=True,
                workspace_id=workspace_id,
                user_id="admin",
                role="admin",
            ),
        ),
        (
            settings.uploader_token,
            SecurityContext(
                actor="Invoice Uploader",
                workspace_id=workspace_id,
                user_id="uploader",
                role="uploader",
            ),
        ),
        (
            settings.reviewer_token,
            SecurityContext(
                actor="Invoice Reviewer",
                workspace_id=workspace_id,
                user_id="reviewer",
                role="reviewer",
            ),
        ),
    )
    for expected_token, context in principals:
        if expected_token and compare_digest(provided_token, expected_token):
            return context
    raise UnauthorizedError("Invalid access token")


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
