from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.dependencies import AppContainer, get_container
from app.core.security import SecurityContext, UnauthorizedError, authenticate_access_token
from app.core.settings import is_hosted


SESSION_COOKIE = "doc_intel_admin_token"
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    access_token: str


@router.post("/session")
def create_session(
    payload: LoginPayload,
    response: Response,
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        context = authenticate_access_token(payload.access_token, container.settings)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        ) from exc
    session_id = container.sessions.create(context)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=is_hosted(container.settings),
        samesite="strict",
        max_age=container.settings.session_ttl_seconds,
        path="/",
    )
    return _session_payload(context)


@router.get("/session")
def get_session(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    context = container.sessions.get(session_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return _session_payload(context)


@router.delete("/session")
def delete_session(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    container: AppContainer = Depends(get_container),
) -> dict[str, bool]:
    container.sessions.revoke(session_id)
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=is_hosted(container.settings),
        samesite="strict",
    )
    return {"authenticated": False}


def _session_payload(context: SecurityContext) -> dict[str, object]:
    return {
        "authenticated": True,
        "actor": context.actor,
        "user_id": context.user_id,
        "workspace_id": context.workspace_id,
        "role": context.role,
        "is_admin": context.is_admin,
    }
