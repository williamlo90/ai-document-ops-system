from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container, require_context
from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext
from app.validation.document import validate_for_review


router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("/{document_id}/workflow", operation_id="getInvoiceWorkflow")
def invoice_workflow(document_id: UUID, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, object]:
    document = container.persistence.documents.get(document_id)
    record = container.persistence.reviews.get(document_id)
    if document is None or record is None or document.workspace_id != context.workspace_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    report = validate_for_review(record.current)
    return {
        "document_id": str(document_id),
        "status": document.status.value,
        "blocking_issues": [issue.code for issue in report.issues if issue.severity.value == "error"],
        "correction_count": len(container.persistence.corrections.list_for_document(document_id)),
    }
