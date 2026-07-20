from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import AppContainer, get_container, require_review_context
from app.api.document_workflow import current_work_item, extraction_or_none
from app.api.serializers import document_response, review_task_response
from app.backoffice.workflow_projection import project_workflow
from app.core.security import SecurityContext
from app.documents.repositories import NotFoundError
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.extraction.schemas import InvoiceData, InvoiceLineItem
from app.review.corrections import correction_event_to_dict


router = APIRouter(prefix="/review", tags=["review"])


class CorrectedLineItemPayload(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class CorrectedInvoicePayload(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: list[CorrectedLineItemPayload] = Field(default_factory=list)


class ReviewSavePayload(BaseModel):
    notes: str = ""
    corrected_data: CorrectedInvoicePayload | None = None


class RejectPayload(BaseModel):
    notes: str = Field(min_length=3, max_length=1000)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("A rejection reason is required")
        return normalized


@router.get("/queue")
def review_queue(
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> list[dict[str, object]]:
    return [
        document_response(document) for document in container.review_service.list_queue(context)
    ]


@router.get("/worklist")
def review_worklist(
    search: str = Query(default="", max_length=120),
    vendor: str = Query(default="", max_length=120),
    owner: str = Query(default="", max_length=120),
    risk: str = Query(default="", pattern="^(|high|medium|low)$"),
    sort: str = Query(default="updated", pattern="^(updated|risk|confidence|due_date)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    rows = [
        _review_worklist_row(document, context, container)
        for document in container.review_service.list_queue(context)
    ]
    needle = search.strip().casefold()
    vendor_filter = vendor.strip().casefold()
    owner_filter = owner.strip().casefold()
    filtered = [
        row
        for row in rows
        if (
            not needle
            or needle
            in " ".join(
                str(row.get(key) or "")
                for key in ("invoice_number", "vendor_name", "original_filename")
            ).casefold()
        )
        and (not vendor_filter or vendor_filter in str(row["vendor_name"] or "").casefold())
        and (not owner_filter or owner_filter in str(row["owner"] or "").casefold())
        and (not risk or row["risk"] == risk)
    ]
    risk_order = {"low": 1, "medium": 2, "high": 3}
    def sort_value(row: dict[str, object]) -> object:
        if sort == "risk":
            return risk_order[str(row["risk"])]
        if sort == "confidence":
            return row["confidence"] if row["confidence"] is not None else -1
        if sort == "due_date":
            return row["due_date"] or ""
        return row["updated_at"]

    filtered.sort(key=sort_value, reverse=direction == "desc")
    today = datetime.now(UTC).date().isoformat()
    total = len(filtered)
    start = (page - 1) * page_size
    return {
        "items": filtered[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "summary": {
            "in_queue": total,
            "high_risk": sum(row["risk"] == "high" for row in filtered),
            "invoice_due_today": sum(row["due_date"] == today for row in filtered),
            "average_review_seconds": None,
        },
    }


def _review_worklist_row(document, context: SecurityContext, container: AppContainer) -> dict[str, object]:
    extraction = extraction_or_none(container, document.id)
    data = extraction.extraction_result.extraction.data if extraction else None
    issues = extraction.validation_report.issues if extraction else ()
    blockers = [issue for issue in issues if issue.severity.value == "error"]
    confidence_values = [
        item.score
        for item in extraction.extraction_result.extraction.confidence
        if item.score is not None
    ] if extraction else []
    confidence = (
        round(sum(float(value) for value in confidence_values) / len(confidence_values), 4)
        if confidence_values
        else None
    )
    work_item = current_work_item(container, context, document.id)
    projection = project_workflow(document, work_item, container.backoffice_approvals)
    try:
        review_task = container.reviews.get_for_document(document.id)
    except NotFoundError:
        review_task = None
    risk = "high" if blockers else "medium" if issues else "low"
    finding = blockers[0].message if blockers else issues[0].message if issues else None
    return {
        **document_response(document),
        "invoice_number": data.invoice_number if data else None,
        "vendor_name": data.vendor_name if data else None,
        "total": str(data.total) if data and data.total is not None else None,
        "currency": data.currency if data else None,
        "invoice_date": data.invoice_date.isoformat() if data and data.invoice_date else None,
        "due_date": data.due_date.isoformat() if data and data.due_date else None,
        "owner": review_task.assigned_to if review_task and review_task.assigned_to else projection.current_owner,
        "risk": risk,
        "confidence": confidence,
        "finding": finding,
        "blocker_count": len(blockers),
        "issue_count": len(issues),
        "can_approve": not blockers,
        "recommended_action": "request_correction" if blockers else "review",
        "age_seconds": max(0, int((datetime.now(UTC) - document.updated_at).total_seconds())),
    }


@router.get("/{document_id}/corrections")
def correction_history(
    document_id: UUID,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        document = container.documents.get(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if document.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    events = container.correction_feedback.list_for_document(document_id, context)
    return {
        "document_id": str(document_id),
        "corrections": [correction_event_to_dict(event) for event in events],
    }


@router.post("/{document_id}/save")
def save_review(
    document_id: UUID,
    payload: ReviewSavePayload,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        corrected_data = _invoice_data(payload.corrected_data) if payload.corrected_data else None
        task = container.review_service.save_review(
            document_id,
            notes=payload.notes,
            context=context,
            corrected_data=corrected_data,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"review_task": review_task_response(task)}


@router.post("/{document_id}/approve")
def approve_review(
    document_id: UUID,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        task = container.review_service.approve(document_id, context=context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _decision_response(document_id, task, container)


@router.post("/{document_id}/reject")
def reject_review(
    document_id: UUID,
    payload: RejectPayload,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        task = container.review_service.reject(document_id, notes=payload.notes, context=context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _decision_response(document_id, task, container)


def _invoice_data(payload: CorrectedInvoicePayload) -> InvoiceData:
    return InvoiceData(
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


def _decision_response(document_id: UUID, task, container: AppContainer) -> dict[str, object]:
    document = container.documents.get(document_id)
    audit_events = container.audits.list_for_document(document_id)
    export_eligibility = (
        "eligible" if document.status == DocumentStatus.APPROVED else "not_eligible"
    )
    return {
        "review_task": review_task_response(task),
        "document": document_response(document),
        "decision": {
            "status": task.status,
            "actor": task.reviewed_by,
            "recorded_at": task.reviewed_at.isoformat() if task.reviewed_at else None,
            "note": task.reviewer_notes,
            "audit_event_count": len(audit_events),
            "export_eligibility": export_eligibility,
        },
    }
