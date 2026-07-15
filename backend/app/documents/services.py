from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.security import (
    INTAKE_ROLES,
    SecurityContext,
    is_intake_role,
    require_admin,
    require_any_role,
)
from app.core.upload_scanning import SignatureUploadScanner, UploadScanner
from app.core.observability import OperationEvent, log_operation
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
    NotFoundError,
)
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import DocumentSource, ExtractorProvider, ParserProvider, ProviderError
from app.providers.storage import DocumentStorage
from app.validation.document import validate_document_invoice


@dataclass(frozen=True)
class UploadResult:
    document: DocumentRecord
    job: ProcessingJob


class DocumentUploadService:
    def __init__(
        self,
        storage: DocumentStorage,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        upload_scanner: UploadScanner | None = None,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.workflow = workflow
        self.upload_scanner = upload_scanner or SignatureUploadScanner()

    def upload_pdf(
        self,
        original_filename: str,
        content_type: str,
        chunks: list[bytes],
        context: SecurityContext,
    ) -> UploadResult:
        require_any_role(context, {"admin", *INTAKE_ROLES})
        stored = self.storage.save_upload_stream(
            original_filename, content_type, self.upload_scanner.scan(chunks)
        )
        document = self.documents.add(
            DocumentRecord(
                original_filename=stored.original_filename,
                storage_key=stored.storage_key,
                content_type=stored.content_type,
                workspace_id=context.workspace_id,
                submitted_by=context.user_id,
                size_bytes=stored.size_bytes,
            )
        )
        self.audits.add(self.workflow.record_upload(document, actor=context.actor))
        self.audits.add(
            self.workflow.transition(document, DocumentStatus.QUEUED, actor=context.actor)
        )
        self.documents.add(document)
        job = self.jobs.add(ProcessingJob(document_id=document.id))
        log_operation(
            OperationEvent(
                event_type="document_uploaded",
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                job_id=str(job.id),
                status=document.status.value,
            )
        )
        return UploadResult(document=document, job=job)


class DocumentProcessingService:
    def __init__(
        self,
        storage: DocumentStorage,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        extractions: ExtractionRepository,
        workflow: DocumentWorkflowService,
        parser: ParserProvider,
        extractor: ExtractorProvider,
        max_processing_attempts: int = 3,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.extractions = extractions
        self.workflow = workflow
        self.parser = parser
        self.extractor = extractor
        self.max_processing_attempts = max_processing_attempts

    def process_job(self, job_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_admin(context)
        job = self.jobs.get(job_id)
        return self._process_job(job, context)

    def process_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_any_role(context, {"admin", *INTAKE_ROLES})
        document = self.documents.get(document_id)
        _require_workspace(document, context)
        _require_owner_for_intake_role(document, context)
        job = self.jobs.get_latest_for_document(document_id)
        return self._process_job(job, context)

    def retry_failed_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_admin(context)
        document = self.documents.get(document_id)
        _require_workspace(document, context)
        if document.status != DocumentStatus.FAILED:
            raise InvalidStatusTransition("Only failed documents can be retried")
        document.error_message = None
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.QUEUED,
                actor=context.actor,
                payload_summary="manual retry requested",
            )
        )
        self.documents.add(document)
        self.jobs.add(ProcessingJob(document_id=document.id))
        return document

    def reprocess_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_admin(context)
        document = self.documents.get(document_id)
        _require_workspace(document, context)
        if document.status not in {
            DocumentStatus.EXTRACTED,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.FAILED,
            DocumentStatus.CANCELLED,
        }:
            raise InvalidStatusTransition(
                "Only extracted, review, failed, or cancelled documents can be reprocessed"
            )
        document.error_message = None
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.QUEUED,
                actor=context.actor,
                payload_summary="manual reprocess requested",
            )
        )
        self.documents.add(document)
        self.jobs.add(ProcessingJob(document_id=document.id))
        return document

    def cancel_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        require_admin(context)
        document = self.documents.get(document_id)
        _require_workspace(document, context)
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
        job.cancel()
        self.jobs.save(job)
        self.audits.add(
            self.workflow.transition(
                document,
                DocumentStatus.CANCELLED,
                actor=context.actor,
                payload_summary="intake cancelled by operator",
            )
        )
        self.documents.add(document)
        return document

    def _process_job(self, job: ProcessingJob, context: SecurityContext) -> DocumentRecord:
        document = self.documents.get(job.document_id)
        _require_workspace(document, context)
        if job.status not in {
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RETRYING,
            ProcessingJobStatus.RUNNING,
        }:
            raise InvalidStatusTransition(f"Cannot process job with status {job.status}")
        if document.status not in {DocumentStatus.QUEUED, DocumentStatus.PROCESSING}:
            raise InvalidStatusTransition(f"Cannot process document with status {document.status}")
        try:
            if job.status != ProcessingJobStatus.RUNNING:
                job.start()
                self.jobs.add(job)
            log_operation(
                OperationEvent(
                    event_type="processing_started",
                    workspace_id=context.workspace_id,
                    actor=context.actor,
                    document_id=str(document.id),
                    job_id=str(job.id),
                    status=job.status.value,
                    attempt_count=job.attempt_count,
                )
            )
            if document.status != DocumentStatus.PROCESSING:
                self.audits.add(
                    self.workflow.transition(
                        document, DocumentStatus.PROCESSING, actor=context.actor
                    )
                )
                self.documents.add(document)
            source = self._document_source(document)
            parsed = self.parser.parse(source)
            if not parsed.text.strip():
                raise ProviderError("empty_document_text", provider_name=self.parser.provider_name)
            result = self.extractor.extract_invoice(parsed)
            report = validate_document_invoice(
                result.extraction.data,
                document,
                self.documents,
                self.extractions,
            )
            self.extractions.save(document.id, result, report)
            self.audits.add(
                self.workflow.transition(document, DocumentStatus.EXTRACTED, actor=context.actor)
            )
            self.documents.add(document)
            self.audits.add(
                self.workflow.transition(
                    document,
                    DocumentStatus.NEEDS_REVIEW,
                    actor=context.actor,
                    payload_summary=(
                        "Validation requires reviewer correction."
                        if report.has_errors
                        else "Invoice is ready for reviewer approval."
                    ),
                )
            )
            self.documents.add(document)
            job.provider_name = result.provider_name
            job.provider_trace_id = result.provider_trace_id
            job.succeed()
            self.jobs.add(job)
            log_operation(
                OperationEvent(
                    event_type="processing_succeeded",
                    workspace_id=context.workspace_id,
                    actor=context.actor,
                    document_id=str(document.id),
                    job_id=str(job.id),
                    provider_name=job.provider_name,
                    status=job.status.value,
                    attempt_count=job.attempt_count,
                )
            )
            return document
        except Exception as exc:
            error_code = _safe_error_code(exc)
            if _should_retry(exc, job, self.max_processing_attempts):
                job.retry(error_code)
                document.error_message = error_code
                self.audits.add(
                    self.workflow.transition(
                        document,
                        DocumentStatus.QUEUED,
                        actor=context.actor,
                        payload_summary=error_code,
                    )
                )
            else:
                if isinstance(exc, ProviderError) and exc.retryable:
                    job.dead_letter(error_code)
                else:
                    job.fail(error_code)
                document.error_message = job.error_message
                if document.status != DocumentStatus.FAILED:
                    self.audits.add(
                        self.workflow.transition(
                            document, DocumentStatus.FAILED, actor=context.actor
                        )
                    )
            self.documents.add(document)
            self.jobs.add(job)
            log_operation(
                OperationEvent(
                    event_type="processing_failed",
                    workspace_id=context.workspace_id,
                    actor=context.actor,
                    document_id=str(document.id),
                    job_id=str(job.id),
                    status=job.status.value,
                    error_code=error_code,
                    retryable=isinstance(exc, ProviderError) and exc.retryable,
                    attempt_count=job.attempt_count,
                )
            )
            return document

    def _document_source(self, document: DocumentRecord) -> DocumentSource:
        path: Path = self.storage.open_for_parser(document.storage_key)
        return DocumentSource(
            storage_key=document.storage_key,
            path=path,
            original_filename=document.original_filename,
            content_type=document.content_type,
        )


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return f"provider_error:{exc.provider_name}"
    return exc.__class__.__name__


def _should_retry(exc: Exception, job: ProcessingJob, max_attempts: int) -> bool:
    return isinstance(exc, ProviderError) and exc.retryable and job.attempt_count < max_attempts


def _require_workspace(document: DocumentRecord, context: SecurityContext) -> None:
    if document.workspace_id != context.workspace_id:
        raise NotFoundError(f"Document not found: {document.id}")


def _require_owner_for_intake_role(document: DocumentRecord, context: SecurityContext) -> None:
    if is_intake_role(context) and document.submitted_by != context.user_id:
        raise NotFoundError(f"Document not found: {document.id}")
