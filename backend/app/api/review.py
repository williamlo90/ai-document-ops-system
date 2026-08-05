from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import get_container, require_context
from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext, UnauthorizedError, require_role
from app.review.services import ApprovalBlocked


router = APIRouter(prefix="/review", tags=["review"])


class CorrectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str
    value: str | None = None
    reason: str = Field(min_length=1, max_length=500)


class DecisionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(min_length=1, max_length=1000)


def _require_reviewer(context: SecurityContext) -> None:
    try:
        require_role(context, "admin", "reviewer")
    except UnauthorizedError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc


@router.patch("/{document_id}/correction", operation_id="correctInvoice")
def correct_invoice(document_id: UUID, payload: CorrectionPayload, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, object]:
    _require_reviewer(context)
    record = container.review_module.service.correct(document_id, field_name=payload.field_name, value=payload.value, actor=context.actor, reason=payload.reason)
    return {"document_id": str(document_id), "field_name": payload.field_name, "value": str(getattr(record.current, payload.field_name))}


@router.post("/{document_id}/approve", operation_id="approveInvoice")
def approve_invoice(document_id: UUID, payload: DecisionPayload, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, str]:
    _require_reviewer(context)
    try:
        event = container.review_module.service.decide(document_id, approve=True, actor=context.actor, note=payload.note)
    except ApprovalBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": event.new_status.value, "actor": event.actor}  # type: ignore[union-attr]


@router.post("/{document_id}/reject", operation_id="rejectInvoice")
def reject_invoice(document_id: UUID, payload: DecisionPayload, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, str]:
    _require_reviewer(context)
    event = container.review_module.service.decide(document_id, approve=False, actor=context.actor, note=payload.note)
    return {"status": event.new_status.value, "actor": event.actor}  # type: ignore[union-attr]
