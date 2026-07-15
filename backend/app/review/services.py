from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.security import SecurityContext, require_any_role
from app.documents.models import AuditEvent, DocumentRecord, ReviewTask
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
    ReviewTaskRepository,
)
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.providers.contracts import ExtractionResult
from app.validation.document import validate_document_invoice


class ReviewService:
    def __init__(
        self,
        documents: DocumentRepository,
        reviews: ReviewTaskRepository,
        extractions: ExtractionRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
    ) -> None:
        self.documents = documents
        self.reviews = reviews
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow

    def list_queue(self, context: SecurityContext) -> list[DocumentRecord]:
        require_any_role(context, {"admin", "reviewer"})
        return self.documents.list_by_workspace_and_status(
            context.workspace_id, DocumentStatus.NEEDS_REVIEW
        )

    def save_review(
        self,
        document_id: UUID,
        notes: str,
        context: SecurityContext,
        corrected_data: InvoiceData | None = None,
    ) -> ReviewTask:
        require_any_role(context, {"admin", "reviewer"})
        document = self.documents.get(document_id)
        self._require_workspace(document, context)
        if document.status != DocumentStatus.NEEDS_REVIEW:
            raise InvalidStatusTransition("Can only save review notes for needs_review documents")
        if corrected_data is not None:
            stored = self.extractions.get_for_document(document_id)
            updated_result = ExtractionResult(
                extraction=InvoiceExtraction(
                    data=corrected_data,
                    schema_version=stored.extraction_result.extraction.schema_version,
                    confidence=stored.extraction_result.extraction.confidence,
                ),
                provider_name=stored.extraction_result.provider_name,
                provider_trace_id=stored.extraction_result.provider_trace_id,
            )
            report = validate_document_invoice(
                corrected_data,
                document,
                self.documents,
                self.extractions,
            )
            self.extractions.save(document_id, updated_result, report)
            self.audits.add(
                AuditEvent(
                    document_id=document_id,
                    event_type="extraction_updated",
                    actor=context.actor,
                    old_status=document.status,
                    new_status=document.status,
                    payload_summary="corrected extraction saved",
                )
            )
        task = self._get_or_create_task(document_id)
        task.reviewer_notes = notes
        task.reviewed_by = context.actor
        task.reviewed_at = datetime.now(UTC)
        task.updated_at = task.reviewed_at
        self.audits.add(
            AuditEvent(
                document_id=document_id,
                event_type="review_saved",
                actor=context.actor,
                old_status=document.status,
                new_status=document.status,
                payload_summary="review notes saved",
            )
        )
        return self.reviews.save(task)

    def approve(self, document_id: UUID, context: SecurityContext) -> ReviewTask:
        require_any_role(context, {"admin", "reviewer"})
        document = self.documents.get(document_id)
        self._require_workspace(document, context)
        if document.status != DocumentStatus.NEEDS_REVIEW:
            raise InvalidStatusTransition("Can only approve needs_review documents through review")
        stored = self.extractions.get_for_document(document_id)
        if stored.validation_report.has_errors:
            raise InvalidStatusTransition("Resolve invoice issues before approving")
        task = self._get_or_create_task(document_id)
        self.audits.add(self.workflow.transition(document, DocumentStatus.APPROVED, context.actor))
        self.documents.add(document)
        task.status = "approved"
        task.reviewed_by = context.actor
        task.reviewed_at = datetime.now(UTC)
        task.updated_at = task.reviewed_at
        return self.reviews.save(task)

    def reject(self, document_id: UUID, notes: str, context: SecurityContext) -> ReviewTask:
        require_any_role(context, {"admin", "reviewer"})
        document = self.documents.get(document_id)
        self._require_workspace(document, context)
        if document.status != DocumentStatus.NEEDS_REVIEW:
            raise InvalidStatusTransition("Can only reject needs_review documents")
        task = self._get_or_create_task(document_id)
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.REJECTED,
                context.actor,
                payload_summary="document rejected",
            )
        )
        self.documents.add(document)
        task.reviewer_notes = notes
        task.status = "rejected"
        task.reviewed_by = context.actor
        task.reviewed_at = datetime.now(UTC)
        task.updated_at = task.reviewed_at
        return self.reviews.save(task)

    def _get_or_create_task(self, document_id: UUID) -> ReviewTask:
        try:
            return self.reviews.get_for_document(document_id)
        except NotFoundError:
            return ReviewTask(document_id=document_id)

    def _require_workspace(self, document: DocumentRecord, context: SecurityContext) -> None:
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document.id}")
