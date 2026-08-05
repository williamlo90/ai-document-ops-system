from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.api.dependencies import get_container, require_context
from app.api.serializers import DocumentResponse
from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext, UnauthorizedError, require_role
from app.documents.models import DocumentRecord


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/intake", operation_id="intakeDocument", response_model=DocumentResponse)
async def intake_document(
    request: Request,
    filename: str = Query(min_length=1, max_length=200),
    context: SecurityContext = Depends(require_context),
    container: AppContainer = Depends(get_container),
) -> DocumentResponse:
    try:
        require_role(context, "admin", "uploader")
    except UnauthorizedError as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc
    content = await request.body()
    result = container.document_module.upload_service.upload(
        content,
        filename=filename,
        workspace_id=context.workspace_id,
        actor=context.actor,
    )
    return _document_response(result.document)


@router.get("/{document_id}/content", operation_id="getDocumentContent")
def get_document_content(
    document_id: UUID,
    context: SecurityContext = Depends(require_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    document = container.persistence.documents.get(document_id)
    if document is None or document.workspace_id != context.workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(
        content=container.document_module.storage.read(document.storage_key),
        media_type="application/pdf",
    )


def _document_response(document: DocumentRecord) -> DocumentResponse:
    return DocumentResponse(
        id=str(document.id),
        original_filename=document.original_filename,
        status=document.status.value,
        workspace_id=document.workspace_id,
        size_bytes=document.size_bytes,
    )
