from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies import AppContainer, get_container
from app.core.security import UnauthorizedError, verify_admin_token
from app.core.settings import is_production_like


SESSION_COOKIE = "doc_intel_admin_token"
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    admin_token: str


@router.post("/session")
def create_session(
    payload: LoginPayload,
    response: Response,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        context = verify_admin_token(payload.admin_token, container.settings.admin_token)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        ) from exc
    session_id = request.app.state.sessions.create(context)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=is_production_like(container.settings),
        samesite="strict",
        max_age=container.settings.session_ttl_seconds,
        path="/",
    )
    return {"authenticated": True, "actor": context.actor, "role": context.role}


@router.get("/session")
def get_session(
    request: Request,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    context = request.app.state.sessions.get(session_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return {"authenticated": True, "actor": context.actor, "role": context.role}


@router.delete("/session")
def delete_session(
    request: Request,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, bool]:
    request.app.state.sessions.revoke(session_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"authenticated": False}
