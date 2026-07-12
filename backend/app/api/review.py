from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import AppContainer, get_container, require_review_context
from app.api.serializers import document_response, review_task_response
from app.core.security import SecurityContext
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition
from app.extraction.schemas import InvoiceData, InvoiceLineItem


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
    notes: str = ""


@router.get("/queue")
def review_queue(
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> list[dict[str, object]]:
    return [
        document_response(document) for document in container.review_service.list_queue(context)
    ]


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
    return {"review_task": review_task_response(task)}


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
    return {"review_task": review_task_response(task)}


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
