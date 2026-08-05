from __future__ import annotations

from typing import cast

from fastapi import Cookie, Depends, HTTPException, Request

from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext, UnauthorizedError, require_role


SESSION_COOKIE = "invoice_review_session"


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def require_context(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    container: AppContainer = Depends(get_container),
) -> SecurityContext:
    context = container.sessions.get(session_id)
    if context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return context


def require_admin(context: SecurityContext = Depends(require_context)) -> SecurityContext:
    try:
        require_role(context, "admin")
    except UnauthorizedError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    return context
