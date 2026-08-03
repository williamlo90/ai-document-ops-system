from __future__ import annotations

from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.transactions import TransactionManager
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.repositories import DocumentRepository, JobRepository, NotFoundError
from app.documents.state_writer import DocumentStateWriter
from app.documents.status import DocumentStatus, InvalidStatusTransition


class DocumentLifecycleCommandService:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        jobs: JobRepository,
        state_writer: DocumentStateWriter,
        transactions: TransactionManager,
    ) -> None:
        self.documents = documents
        self.jobs = jobs
        self.state_writer = state_writer
        self.transactions = transactions

    def retry_failed(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        return self._enqueue(
            document_id,
            context,
            allowed_statuses={DocumentStatus.FAILED},
            invalid_status_message="Only failed documents can be retried",
            audit_summary="manual retry requested",
        )

    def reprocess(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        return self._enqueue(
            document_id,
            context,
            allowed_statuses={
                DocumentStatus.EXTRACTED,
                DocumentStatus.NEEDS_REVIEW,
                DocumentStatus.FAILED,
                DocumentStatus.CANCELLED,
            },
            invalid_status_message=(
                "Only extracted, review, failed, or cancelled documents can be reprocessed"
            ),
            audit_summary="manual reprocess requested",
        )

    def cancel(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_admin(context)
        document = self._document_for_workspace(document_id, context)
        if document.status not in {DocumentStatus.QUEUED, DocumentStatus.FAILED}:
            raise InvalidStatusTransition("Only queued or failed intake can be cancelled")
        job = self.jobs.get_latest_for_document(document_id)
        if job.status not in {
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RETRYING,
            ProcessingJobStatus.FAILED,
            ProcessingJobStatus.DEAD_LETTER,
        }:
            raise InvalidStatusTransition("Active processing cannot be cancelled")
        with self.transactions.transaction():
            job.cancel()
            self.jobs.save(job)
            self.state_writer.transition(
                document,
                DocumentStatus.CANCELLED,
                actor=context.actor,
                payload_summary="intake cancelled by operator",
            )
        return document

    def _enqueue(
        self,
        document_id: UUID,
        context: SecurityContext,
        *,
        allowed_statuses: set[DocumentStatus],
        invalid_status_message: str,
        audit_summary: str,
    ) -> DocumentRecord:
        require_admin(context)
        document = self._document_for_workspace(document_id, context)
        if document.status not in allowed_statuses:
            raise InvalidStatusTransition(invalid_status_message)
        document.error_message = None
        with self.transactions.transaction():
            self.state_writer.transition(
                document,
                DocumentStatus.QUEUED,
                actor=context.actor,
                payload_summary=audit_summary,
            )
            self.jobs.add(ProcessingJob(document_id=document.id))
        return document

    def _document_for_workspace(
        self,
        document_id: UUID,
        context: SecurityContext,
    ) -> DocumentRecord:
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document.id}")
        return document
