from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.http_headers import NO_STORE_HEADERS
from app.core.security import SecurityContext
from app.exports.models import (
    ExportBatchNotFound,
    ExportEligibilityError,
    ExportIdempotencyConflict,
    ExportRunNotFound,
)


router = APIRouter(prefix="/exports", tags=["exports"])


class ExportBatchPayload(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=100)
    mode: str = Field(default="ready", pattern="^(ready|draft)$")
    name: str | None = Field(default=None, max_length=120)


@router.get("/workspace")
def export_workspace(
    view: str = Query(default="ready", pattern="^(ready|in_batch|exported|blocked|drafts)$"),
    search: str = Query(default="", max_length=120),
    vendor: str = Query(default="", max_length=120),
    currency: str = Query(default="", max_length=12),
    approved_by: str = Query(default="", max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    batch_id: UUID | None = Query(default=None),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.export_batch_service.workspace(
            context=context,
            view=view,
            search=search,
            vendor=vendor,
            currency=currency,
            approved_by=approved_by,
            page=page,
            page_size=page_size,
            batch_id=batch_id,
        )
    except ExportBatchNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/batches")
def create_export_batch(
    payload: ExportBatchPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.export_batch_service.create_batch(
            context=context,
            document_ids=tuple(payload.document_ids),
            mode=payload.mode,
            name=payload.name,
        )
    except ExportEligibilityError as exc:
        raise _eligibility_conflict(exc) from exc


@router.patch("/batches/{batch_id}")
def update_export_batch(
    batch_id: UUID,
    payload: ExportBatchPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.export_batch_service.update_batch(
            context=context,
            batch_id=batch_id,
            document_ids=tuple(payload.document_ids),
            mode=payload.mode,
            name=payload.name,
        )
    except ExportBatchNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExportEligibilityError as exc:
        raise _eligibility_conflict(exc) from exc


@router.get("/batches/{batch_id}/eligibility")
def export_batch_eligibility(
    batch_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        batch = container.export_batches.get_batch(context.workspace_id, batch_id)
        if batch is None:
            raise ExportBatchNotFound("Export batch not found.")
        checks = container.export_batch_service.eligibility(context=context, batch=batch)
        return {"eligible": all(check["state"] == "passed" for check in checks), "checks": checks}
    except ExportBatchNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/batches/{batch_id}/execute")
def execute_export_batch(
    batch_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        run = container.export_batch_service.execute(
            context=context,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
        )
        return {"run": container.export_batch_service.run_response(run)}
    except ExportBatchNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExportEligibilityError as exc:
        raise _eligibility_conflict(exc) from exc
    except ExportIdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/runs")
def list_export_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    runs = container.export_batches.list_runs(context.workspace_id)
    start = (page - 1) * page_size
    return {
        "items": [container.export_batch_service.run_response(run) for run in runs[start : start + page_size]],
        "page": page,
        "page_size": page_size,
        "total": len(runs),
        "total_pages": max(1, (len(runs) + page_size - 1) // page_size),
    }


@router.get("/runs/{run_id}")
def export_run_detail(
    run_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return {"run": container.export_batch_service.run_detail(context, run_id)}
    except ExportRunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/runs/{run_id}/download")
def download_export_run(
    run_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    try:
        file_name, csv_text = container.export_batch_service.artifact(context, run_id)
    except ExportRunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )


@router.post("/runs/{run_id}/retry")
def retry_export_run(
    run_id: UUID,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        run = container.export_batch_service.retry(
            context=context,
            run_id=run_id,
            idempotency_key=idempotency_key,
        )
        return {"run": container.export_batch_service.run_response(run)}
    except ExportRunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ExportEligibilityError as exc:
        raise _eligibility_conflict(exc) from exc
    except ExportIdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/invoices.csv")
def export_invoices_csv(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    csv_text = container.export_service.export_approved_csv(context=context)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": 'attachment; filename="invoices.csv"',
        },
    )


@router.get("/predictions.json")
def export_predictions_json(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    json_text = container.export_service.export_predictions_json(context=context)
    return Response(
        content=json_text,
        media_type="application/json",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": 'attachment; filename="predictions.json"',
        },
    )


def _eligibility_conflict(exc: ExportEligibilityError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"message": str(exc), "checks": list(exc.checks)},
    )
