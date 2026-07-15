from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.document_commands import (
    WorkflowCommandPayload,
    cancel_document_command,
    escalate_document_command,
    reprocess_document_command,
    request_document_correction_command,
    retry_document_command,
)
from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.document_workflow import (
    current_work_item,
    document_for_context,
    document_workflow_response,
    extraction_or_none,
)
from app.api.serializers import document_response, extraction_response
from app.backoffice.workflow_projection import project_workflow
from app.core.security import SecurityContext
from app.core.security import is_intake_role
from app.documents.models import AuditEvent
from app.documents.repositories import StoredExtraction
from app.documents.status import DocumentStatus
from app.extraction.schemas import InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult
from app.review.models import CorrectionSource
from app.validation.document import validate_document_invoice


router = APIRouter(prefix="/invoices", tags=["invoice-workflow"])


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
    correction_reason: str | None = Field(default=None, max_length=500)


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
    extractions = {
        document.id: extraction_or_none(container, document.id) for document in documents
    }
    needle = search.strip().casefold()
    normalized_status = status_filter.strip().casefold()
    normalized_submitter = submitted_by.strip().casefold()
    filtered = [
        document
        for document in documents
        if _matches_invoice_search(document.original_filename, extractions[document.id], needle)
        and _matches_invoice_status(document.status, extractions[document.id], normalized_status)
        and (not normalized_submitter or document.submitted_by.casefold() == normalized_submitter)
        and (not is_intake_role(context) or document.submitted_by == context.user_id)
        and (created_from is None or document.created_at.date() >= created_from)
        and (created_to is None or document.created_at.date() <= created_to)
    ]
    filtered.sort(key=lambda document: document.created_at, reverse=True)
    total = len(filtered)
    start = (page - 1) * page_size
    items = []
    for document in filtered[start : start + page_size]:
        work_item = current_work_item(container, context, document.id)
        projection = project_workflow(document, work_item, container.backoffice_approvals)
        extraction = extractions[document.id]
        issues = extraction.validation_report.issues if extraction else ()
        error_issues = tuple(issue for issue in issues if issue.severity.value == "error")
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
                "business_status": _invoice_business_status(
                    document.status,
                    bool(error_issues) or projection.current_stage == "correction_requested",
                ),
                "validation_issue_count": len(issues),
                "validation_error_count": len(error_issues),
                "has_validation_errors": bool(error_issues),
                "validation_codes": sorted({issue.code for issue in error_issues}),
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
    return document_workflow_response(container, context, document_id)


@router.post("/{document_id}/draft")
def save_intake_draft(
    document_id: UUID,
    payload: IntakeDraftPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    document = document_for_context(container, context, document_id)
    if document.status in {
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
        DocumentStatus.EXPORTED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finalized invoices cannot be edited.",
        )
    stored = extraction_or_none(container, document_id)
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
    work_item = current_work_item(container, context, document_id)
    requested_reason = (
        work_item.business_context.get("correction_reason")
        if work_item and work_item.business_context.get("correction_state") == "requested"
        else None
    )
    correction = container.correction_feedback.capture(
        workspace_id=document.workspace_id,
        document_id=document_id,
        before=stored.extraction_result.extraction.data,
        after=data,
        actor=context.actor,
        reason=payload.correction_reason,
        requested_reason=requested_reason,
        source=CorrectionSource.INTAKE_CHECK,
    )
    saved = container.extractions.save(
        document_id,
        updated,
        validate_document_invoice(
            data,
            document,
            container.documents,
            container.extractions,
        ),
    )
    container.audits.add(
        AuditEvent(
            document_id=document_id,
            event_type="intake_draft_saved",
            actor=context.actor,
            old_status=document.status,
            new_status=document.status,
            payload_summary=(
                f"Invoice data saved with {len(correction.changes)} corrected fields."
                if correction
                else "Invoice data checked with no field changes."
            ),
        )
    )
    if correction and work_item:
        container.backoffice_service.submit_correction(
            work_item_id=work_item.id,
            context=context,
            change_count=len(correction.changes),
        )
    return {
        "extraction": extraction_response(saved),
        "correction_recorded": correction is not None,
        "correction_summary": container.correction_feedback.summary(
            document.workspace_id, document_id
        ),
    }


def _matches_invoice_search(
    filename: str,
    extraction: StoredExtraction | None,
    needle: str,
) -> bool:
    if not needle:
        return True
    data = extraction.extraction_result.extraction.data if extraction else None
    searchable = " ".join(
        value
        for value in (
            filename,
            data.vendor_name if data else None,
            data.invoice_number if data else None,
        )
        if value
    ).casefold()
    return needle in searchable


def _matches_invoice_status(
    status_value: DocumentStatus,
    extraction: StoredExtraction | None,
    expected: str,
) -> bool:
    if not expected:
        return True
    has_errors = bool(extraction and extraction.validation_report.has_errors)
    return _invoice_business_status(status_value, has_errors) == expected


def _invoice_business_status(status_value: DocumentStatus, has_errors: bool) -> str:
    if status_value == DocumentStatus.FAILED:
        return "needs_correction"
    if status_value == DocumentStatus.NEEDS_REVIEW and has_errors:
        return "needs_correction"
    return status_value.value


@router.post("/{document_id}/retry")
def retry_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return retry_document_command(document_id, context, container)


@router.post("/{document_id}/reprocess")
def reprocess_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return reprocess_document_command(document_id, context, container)


@router.post("/{document_id}/cancel")
def cancel_invoice(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return cancel_document_command(document_id, context, container)


@router.post("/{document_id}/request-correction")
def request_invoice_correction(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return request_document_correction_command(document_id, payload, context, container)


@router.post("/{document_id}/escalate")
def escalate_invoice(
    document_id: UUID,
    payload: WorkflowCommandPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return escalate_document_command(document_id, payload, context, container)
