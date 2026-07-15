from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.document_commands import (
    WorkflowCommandPayload,
    cancel_document_command,
    escalate_document_command,
    reprocess_document_command,
    request_document_correction_command,
    retry_document_command,
)
from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.document_workflow import document_workflow_response
from app.api.serializers import audit_response, document_response, extraction_response, job_response
from app.core.security import SecurityContext, UnauthorizedError, is_intake_role
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition
from app.providers.storage import StorageError


router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/upload-policy")
def upload_policy(
    filename: str = Query(default=""),
    size_bytes: int = Query(default=0, ge=0),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    duplicates = [
        document_response(document)
        for document in container.documents.list_by_workspace(context.workspace_id)
        if document.original_filename.casefold() == filename.casefold()
        and (size_bytes == 0 or document.size_bytes == size_bytes)
        and _document_visible_to_context(document, context)
    ]
    return {
        "accepted_content_types": ["application/pdf"],
        "max_upload_bytes": container.settings.max_upload_bytes,
        "duplicates": duplicates,
    }


@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        file.file.seek(0)
        chunks = iter(lambda: file.file.read(1024 * 1024), b"")
        result = container.upload_service.upload_pdf(
            original_filename=file.filename or "upload.pdf",
            content_type=file.content_type or "",
            chunks=chunks,
            context=context,
        )
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    return {
        "document": document_response(result.document),
        "job": job_response(result.job),
    }


@router.get("")
def list_documents(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> list[dict[str, object]]:
    return [
        document_response(document)
        for document in container.documents.list_by_workspace(context.workspace_id)
        if _document_visible_to_context(document, context)
    ]


@router.get("/{document_id}")
def get_document(
    document_id: UUID,
    _context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.documents.get(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if document.workspace_id != _context.workspace_id or not _document_visible_to_context(
        document, _context
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    extraction = None
    try:
        extraction = container.extractions.get_for_document(document_id)
    except NotFoundError:
        pass
    return {
        "document": document_response(document),
        "extraction": extraction_response(extraction),
        "correction_summary": container.correction_feedback.summary(
            document.workspace_id, document_id
        ),
        "audit_events": [
            audit_response(event) for event in container.audits.list_for_document(document_id)
        ],
    }


@router.get("/{document_id}/workflow")
def document_workflow(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return document_workflow_response(container, context, document_id)


@router.post("/{document_id}/retry")
def retry_document(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return retry_document_command(document_id, context, container)


@router.post("/{document_id}/reprocess")
def reprocess_document(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return reprocess_document_command(document_id, context, container)


@router.post("/{document_id}/cancel")
def cancel_document(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return cancel_document_command(document_id, context, container)


@router.post("/{document_id}/request-correction")
def request_document_correction(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return request_document_correction_command(document_id, payload, context, container)


@router.post("/{document_id}/escalate")
def escalate_document(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return escalate_document_command(document_id, payload, context, container)


@router.get("/{document_id}/content")
def get_document_content(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> FileResponse:
    try:
        document = container.documents.get(document_id)
        if document.workspace_id != context.workspace_id or not _document_visible_to_context(
            document, context
        ):
            raise NotFoundError("Not found")
        path = container.storage.open_for_parser(document.storage_key)
    except (NotFoundError, StorageError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=document.original_filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/download-url")
def get_document_download_url(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.documents.get(document_id)
        if document.workspace_id != context.workspace_id or not _document_visible_to_context(
            document, context
        ):
            raise NotFoundError("Not found")
        signed_url = container.storage.create_download_url(
            document.storage_key, expires_seconds=300
        )
    except (NotFoundError, StorageError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return {
        "document_id": str(document.id),
        "url": signed_url or f"/documents/{document.id}/content",
        "signed": signed_url is not None,
        "expires_seconds": 300 if signed_url is not None else None,
    }


@router.post("/{document_id}/process")
def process_document(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.processing_service.process_document(document_id, context=context)
        job = container.jobs.get_latest_for_document(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document), "job": job_response(job)}


def _document_visible_to_context(document, context: SecurityContext) -> bool:
    return not is_intake_role(context) or document.submitted_by == context.user_id
