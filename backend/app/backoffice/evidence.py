from __future__ import annotations

from app.backoffice.models import WorkItem
from app.backoffice.planner import PlanningInput
from app.documents.repositories import DocumentRepository, ExtractionRepository, NotFoundError
from app.documents.status import DocumentStatus
from app.validation.invoice import IssueSeverity


def planning_input_from_evidence(
    *,
    work_item: WorkItem,
    requested_outcome: str | None,
    documents: DocumentRepository,
    extractions: ExtractionRepository,
) -> PlanningInput:
    if not work_item.linked_document_ids:
        return PlanningInput(
            requested_outcome=requested_outcome,
            evidence_sufficient=False,
        )

    document_id = work_item.linked_document_ids[0]
    try:
        document = documents.get(document_id)
    except NotFoundError:
        return PlanningInput(
            requested_outcome=requested_outcome,
            evidence_sufficient=False,
            selected_document_id=document_id,
        )
    if document.workspace_id != work_item.workspace_id:
        raise NotFoundError(f"Document not found: {document_id}")

    try:
        stored = extractions.get_for_document(document_id)
    except NotFoundError:
        stored = None

    usable_statuses = {
        DocumentStatus.EXTRACTED,
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.APPROVED,
        DocumentStatus.EXPORTED,
    }
    missing_fields = (
        tuple(
            dict.fromkeys(
                issue.field_name
                for issue in stored.validation_report.issues
                if issue.severity == IssueSeverity.ERROR
            )
        )
        if stored
        else ()
    )
    return PlanningInput(
        requested_outcome=requested_outcome,
        evidence_sufficient=stored is not None and document.status in usable_statuses,
        approved_for_export=document.status in {DocumentStatus.APPROVED, DocumentStatus.EXPORTED},
        missing_fields=missing_fields,
        selected_document_id=document_id,
    )
