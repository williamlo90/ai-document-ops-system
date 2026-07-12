from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status

from app.api.backoffice import _work_item_detail
from app.api.dependencies import AppContainer
from app.api.serializers import audit_response, document_response, extraction_response
from app.backoffice.models import WorkflowEvent, WorkItem
from app.backoffice.workflow_projection import project_workflow
from app.core.security import SecurityContext, is_intake_role
from app.documents.repositories import NotFoundError


def document_workflow_response(
    container: AppContainer,
    context: SecurityContext,
    document_id: UUID,
) -> dict[str, object]:
    document = document_for_context(container, context, document_id)
    extraction = extraction_or_none(container, document_id)
    work_item = current_work_item(container, context, document_id)
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
        "activity": workflow_activity(container, context, document_id),
    }


def document_for_context(
    container: AppContainer,
    context: SecurityContext,
    document_id: UUID,
):
    try:
        document = container.documents.get(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if document.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if is_intake_role(context) and document.submitted_by != context.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return document


def extraction_or_none(container: AppContainer, document_id: UUID):
    try:
        return container.extractions.get_for_document(document_id)
    except NotFoundError:
        return None


def current_work_item(
    container: AppContainer, context: SecurityContext, document_id: UUID
) -> WorkItem | None:
    matches = [
        item
        for item in container.backoffice_work_items.list_by_workspace(context.workspace_id)
        if document_id in item.linked_document_ids
    ]
    return max(matches, key=lambda item: item.updated_at) if matches else None


def required_work_item(
    container: AppContainer, context: SecurityContext, document_id: UUID
) -> WorkItem:
    document_for_context(container, context, document_id)
    work_item = current_work_item(container, context, document_id)
    if work_item is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document does not have a linked work item.",
        )
    return work_item


def workflow_activity(
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
        "document_uploaded": "Document PDF received.",
        "processing_queued": "Document queued for extraction.",
        "processing_started": "Document extraction started.",
        "processing_finished": "Document extraction completed.",
        "review_required": "Validation requires human review.",
        "document_approved": "Document approved.",
        "document_rejected": "Document rejected.",
        "processing_failed": "Document processing failed.",
        "document_exported": "Document exported.",
        "extraction_updated": "Corrected extraction saved.",
        "review_saved": "Review changes saved.",
        "intake_cancelled": "Document intake cancelled.",
        "intake_draft_saved": "Operator corrections saved.",
    }.get(event_type, event_type.replace("_", " ").capitalize())
