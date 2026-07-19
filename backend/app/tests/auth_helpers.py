from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.auth import SESSION_COOKIE
from app.core.security import SecurityContext


def session_headers(
    client: TestClient,
    *,
    actor: str,
    workspace_id: str = "default",
    user_id: str | None = None,
    role: str = "admin",
    is_admin: bool | None = None,
) -> dict[str, str]:
    resolved_admin = role == "admin" if is_admin is None else is_admin
    context = SecurityContext(
        actor=actor,
        is_admin=resolved_admin,
        workspace_id=workspace_id,
        user_id=user_id or actor,
        role=role,
    )
    session_id = client.app.state.sessions.create(context)
    return {"Cookie": f"{SESSION_COOKIE}={session_id}"}
