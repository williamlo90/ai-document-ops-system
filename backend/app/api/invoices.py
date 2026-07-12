from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.backoffice import _work_item_detail
from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.serializers import audit_response, document_response, extraction_response
from app.backoffice.models import WorkflowEvent, WorkItem
from app.backoffice.workflow_projection import project_workflow
from app.core.security import SecurityContext, UnauthorizedError, require_any_role
from app.documents.models import AuditEvent
from app.documents.repositories import NotFoundError
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult
from app.validation.invoice import validate_invoice


router = APIRouter(prefix="/invoices", tags=["invoice-workflow"])


class WorkflowCommandPayload(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class IntakeLineItemPayload(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class IntakeDraftPayload(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: list[IntakeLineItemPayload] = Field(default_factory=list)


@router.get("")
def list_invoices(
    search: str = Query(default="", max_length=120),
    status_filter: str = Query(default="", alias="status", max_length=40),
    submitted_by: str = Query(default="", max_length=120),
    created_from: date | None = Query(default=None),
    created_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    documents = container.documents.list_by_workspace(context.workspace_id)
    needle = search.strip().casefold()
    normalized_status = status_filter.strip().casefold()
    normalized_submitter = submitted_by.strip().casefold()
    filtered = [
        document
        for document in documents
        if (not needle or needle in document.original_filename.casefold())
        and (not normalized_status or document.status.value == normalized_status)
        and (not normalized_submitter or document.submitted_by.casefold() == normalized_submitter)
        and (created_from is None or document.created_at.date() >= created_from)
        and (created_to is None or document.created_at.date() <= created_to)
    ]
    filtered.sort(key=lambda document: document.created_at, reverse=True)
    total = len(filtered)
    start = (page - 1) * page_size
    items = []
    for document in filtered[start : start + page_size]:
        work_item = _current_work_item(container, context, document.id)
        projection = project_workflow(document, work_item, container.backoffice_approvals)
        extraction = _extraction_or_none(container, document.id)
        response = document_response(document)
        response.update(
            {
                "vendor_name": (
                    extraction.extraction_result.extraction.data.vendor_name if extraction else None
                ),
                "total": (
                    str(extraction.extraction_result.extraction.data.total)
                    if extraction and extraction.extraction_result.extraction.data.total is not None
                    else None
                ),
                "currency": (
                    extraction.extraction_result.extraction.data.currency if extraction else None
                ),
                "current_owner": projection.current_owner,
                "current_stage": projection.current_stage,
                "work_item_id": str(work_item.id) if work_item else None,
            }
        )
        items.append(response)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{document_id}/workflow")
def invoice_workflow(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    document = _document_for_context(container, context, document_id)
    extraction = _extraction_or_none(container, document_id)
    work_item = _current_work_item(container, context, document_id)
    projection = project_workflow(document, work_item, container.backoffice_approvals)
    return {
        "document": document_response(document),
        "extraction": extraction_response(extraction),
        "work_item": (_work_item_detail(container, context, work_item) if work_item else None),
        "current_stage": projection.current_stage,
        "current_owner": projection.current_owner,
        "waiting_for": projection.waiting_for,
        "next_action": projection.next_action,
        "attention_reason": projection.attention_reason,
        "activity": _activity(container, context, document_id),
    }


@router.post("/{document_id}/draft")
def save_intake_draft(
    document_id: UUID,
    payload: IntakeDraftPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    document = _document_for_context(container, context, document_id)
    if document.status in {DocumentStatus.REJECTED, DocumentStatus.EXPORTED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finalized invoices cannot be edited.",
        )
    stored = _extraction_or_none(container, document_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run extraction before saving invoice data.",
        )
    data = InvoiceData(
        vendor_name=payload.vendor_name,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        subtotal=payload.subtotal,
        tax=payload.tax,
        total=payload.total,
        currency=payload.currency,
        line_items=tuple(
            InvoiceLineItem(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
            )
            for item in payload.line_items
        ),
    )
    updated = ExtractionResult(
        extraction=InvoiceExtraction(
            data=data,
            schema_version=stored.extraction_result.extraction.schema_version,
            confidence=stored.extraction_result.extraction.confidence,
        ),
        provider_name=stored.extraction_result.provider_name,
        provider_trace_id=stored.extraction_result.provider_trace_id,
    )
    saved = container.extractions.save(document_id, updated, validate_invoice(data))
    container.audits.add(
        AuditEvent(
            document_id=document_id,
            event_type="intake_draft_saved",
            actor=context.actor,
            old_status=document.status,
            new_status=document.status,
            payload_summary="Operator corrections saved as an intake draft.",
        )
    )
    return {"extraction": extraction_response(saved)}


@router.post("/{document_id}/retry")
def retry_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.processing_service.retry_failed_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


@router.post("/{document_id}/reprocess")
def reprocess_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.processing_service.reprocess_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


@router.post("/{document_id}/cancel")
def cancel_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.processing_service.cancel_document(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"document": document_response(document)}


@router.post("/{document_id}/request-correction")
def request_invoice_correction(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _require_role(context, {"admin", "reviewer"})
    work_item = _required_work_item(container, context, document_id)
    updated = container.backoffice_service.request_correction(
        work_item_id=work_item.id,
        context=context,
        notes=payload.reason,
    )
    return {"work_item": _work_item_detail(container, context, updated)}


@router.post("/{document_id}/escalate")
def escalate_invoice(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _require_role(context, {"admin", "operator", "reviewer"})
    work_item = _required_work_item(container, context, document_id)
    updated = container.backoffice_service.escalate_work_item(
        work_item_id=work_item.id,
        context=context,
        reason=payload.reason,
    )
    return {"work_item": _work_item_detail(container, context, updated)}


def _document_for_context(container: AppContainer, context: SecurityContext, document_id: UUID):
    try:
        document = container.documents.get(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if document.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return document


def _extraction_or_none(container: AppContainer, document_id: UUID):
    try:
        return container.extractions.get_for_document(document_id)
    except NotFoundError:
        return None


def _current_work_item(
    container: AppContainer, context: SecurityContext, document_id: UUID
) -> WorkItem | None:
    matches = [
        item
        for item in container.backoffice_work_items.list_by_workspace(context.workspace_id)
        if document_id in item.linked_document_ids
    ]
    return max(matches, key=lambda item: item.updated_at) if matches else None


def _required_work_item(
    container: AppContainer, context: SecurityContext, document_id: UUID
) -> WorkItem:
    _document_for_context(container, context, document_id)
    work_item = _current_work_item(container, context, document_id)
    if work_item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice does not have a linked work item.",
        )
    return work_item


def _activity(
    container: AppContainer, context: SecurityContext, document_id: UUID
) -> list[dict[str, object]]:
    document_events = [
        {
            **audit_response(event),
            "source": "document",
            "summary": event.payload_summary or _document_event_summary(event.event_type),
            "work_item_id": None,
        }
        for event in container.audits.list_for_document(document_id)
    ]
    workflow_events = [
        _workflow_event_response(event)
        for event in container.workflow_events.list_for_document(context.workspace_id, document_id)
    ]
    return sorted(
        [*document_events, *workflow_events],
        key=lambda event: str(event["created_at"]),
    )


def _workflow_event_response(event: WorkflowEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "event_type": event.event_type,
        "actor": event.actor,
        "summary": event.summary,
        "source": "backoffice",
        "document_id": str(event.document_id) if event.document_id else None,
        "work_item_id": str(event.work_item_id) if event.work_item_id else None,
        "created_at": event.created_at.isoformat(),
    }


def _document_event_summary(event_type: str) -> str:
    return {
        "document_uploaded": "Invoice PDF received.",
        "processing_queued": "Invoice queued for extraction.",
        "processing_started": "Invoice extraction started.",
        "processing_finished": "Invoice extraction completed.",
        "review_required": "Validation requires human review.",
        "document_approved": "Invoice document approved.",
        "document_rejected": "Invoice document rejected.",
        "processing_failed": "Invoice processing failed.",
        "document_exported": "Invoice exported.",
        "extraction_updated": "Corrected extraction saved.",
        "review_saved": "Review changes saved.",
        "intake_cancelled": "Invoice intake cancelled.",
        "intake_draft_saved": "Operator corrections saved.",
    }.get(event_type, event_type.replace("_", " ").capitalize())


def _require_role(context: SecurityContext, roles: set[str]) -> None:
    try:
        require_any_role(context, roles)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
