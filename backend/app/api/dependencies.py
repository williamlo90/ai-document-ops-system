from __future__ import annotations

from typing import cast

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.bootstrap.container import AppContainer, build_container
from app.core.security import (
    SecurityContext,
    UnauthorizedError,
    authenticate_access_token,
    authenticate_metrics_token,
    require_any_role,
)

__all__ = ["AppContainer", "build_container"]


def get_container(request: Request) -> AppContainer:
    return cast(AppContainer, request.app.state.container)


def require_authenticated_context(
    request: Request,
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    session_id: str | None = Cookie(default=None, alias="doc_intel_admin_token"),
) -> SecurityContext:
    container = get_container(request)
    session_context = container.sessions.get(session_id)
    if session_context is not None:
        return session_context
    try:
        return authenticate_access_token(x_access_token or x_admin_token, container.settings)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from exc


def require_admin_context(
    context: SecurityContext = Depends(require_authenticated_context),
) -> SecurityContext:
    try:
        require_any_role(context, {"admin"})
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    return context


def require_metrics_token(
    request: Request,
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
) -> None:
    settings = get_container(request).settings
    try:
        authenticate_metrics_token(x_metrics_token, settings)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from exc


def require_review_context(
    context: SecurityContext = Depends(require_authenticated_context),
) -> SecurityContext:
    try:
        require_any_role(context, {"admin", "reviewer"})
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    return context
