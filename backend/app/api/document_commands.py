from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from app.api.backoffice import _work_item_detail
from app.api.dependencies import AppContainer
from app.api.document_workflow import required_work_item
from app.api.serializers import document_response
from app.core.security import SecurityContext, UnauthorizedError, require_any_role
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition


class WorkflowCommandPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def retry_document_command(
    document_id: UUID,
    context: SecurityContext,
    container: AppContainer,
) -> dict[str, object]:
    try:
        document = container.processing_service.retry_failed_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


def reprocess_document_command(
    document_id: UUID,
    context: SecurityContext,
    container: AppContainer,
) -> dict[str, object]:
    try:
        document = container.processing_service.reprocess_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


def cancel_document_command(
    document_id: UUID,
    context: SecurityContext,
    container: AppContainer,
) -> dict[str, object]:
    try:
        document = container.processing_service.cancel_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


def request_document_correction_command(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext,
    container: AppContainer,
) -> dict[str, object]:
    _require_role(context, {"admin", "reviewer"})
    work_item = required_work_item(container, context, document_id)
    updated = container.backoffice_service.request_correction(
        work_item_id=work_item.id,
        context=context,
        notes=payload.reason,
    )
    return {"work_item": _work_item_detail(container, context, updated)}


def escalate_document_command(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext,
    container: AppContainer,
) -> dict[str, object]:
    _require_role(context, {"admin", "operator", "reviewer"})
    work_item = required_work_item(container, context, document_id)
    updated = container.backoffice_service.escalate_work_item(
        work_item_id=work_item.id,
        context=context,
        reason=payload.reason,
    )
    return {"work_item": _work_item_detail(container, context, updated)}


def _require_role(context: SecurityContext, roles: set[str]) -> None:
    try:
        require_any_role(context, roles)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
