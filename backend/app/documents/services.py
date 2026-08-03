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
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.processing_policy import ProcessingRetryPolicy
from app.documents.processing_results import ProcessingResultRecorder
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
    LeaseLostError,
    NotFoundError,
)
from app.documents.status import DocumentStatus, InvalidStatusTransition
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import (
    DocumentSource,
    ExtractionResult,
    ExtractorProvider,
    ParserProvider,
    ProviderError,
)
from app.providers.storage import DocumentStorage
from app.validation.document import validate_document_invoice
from app.validation.invoice import ValidationIssue, ValidationReport
from app.validation.untrusted_content import validate_untrusted_extraction


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
        transactions: TransactionManager | None = None,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.workflow = workflow
        self.upload_scanner = upload_scanner or SignatureUploadScanner()
        self.transactions = transactions or NoopTransactionManager()

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
        try:
            with self.transactions.transaction():
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
        except Exception:
            try:
                self.storage.delete(stored.storage_key)
            except Exception as cleanup_exc:
                raise RuntimeError(
                    "Upload metadata failed and the stored object could not be removed"
                ) from cleanup_exc
            raise
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
        retry_base_seconds: int = 5,
        retry_max_seconds: int = 300,
        transactions: TransactionManager | None = None,
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
        self.retry_base_seconds = max(1, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)
        self.transactions = transactions or NoopTransactionManager()
        self.retry_policy = ProcessingRetryPolicy(
            max_attempts=self.max_processing_attempts,
            base_seconds=self.retry_base_seconds,
            max_seconds=self.retry_max_seconds,
        )
        self.result_recorder = ProcessingResultRecorder(
            documents=self.documents,
            jobs=self.jobs,
            audits=self.audits,
            extractions=self.extractions,
            workflow=self.workflow,
            retry_policy=self.retry_policy,
            transactions=self.transactions,
        )

    def process_job(
        self,
        job_id: UUID,
        context: SecurityContext,
        *,
        lease_token: str | None = None,
    ) -> DocumentRecord:
        require_admin(context)
        job = self.jobs.get(job_id)
        if lease_token is not None and job.lease_token != lease_token:
            raise LeaseLostError(f"Processing job lease was lost: {job.id}")
        return self._process_job(job, context, claimed_lease_token=lease_token)

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
        with self.transactions.transaction():
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
        with self.transactions.transaction():
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
        with self.transactions.transaction():
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

    def _process_job(
        self,
        job: ProcessingJob,
        context: SecurityContext,
        *,
        claimed_lease_token: str | None = None,
    ) -> DocumentRecord:
        document = self.documents.get(job.document_id)
        _require_workspace(document, context)
        self._require_processable_job_status(job)
        if document.status not in {DocumentStatus.QUEUED, DocumentStatus.PROCESSING}:
            raise InvalidStatusTransition(f"Cannot process document with status {document.status}")
        job, lease_token = self._active_job_lease(job, claimed_lease_token)
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
            with self.transactions.transaction():
                self.audits.add(
                    self.workflow.transition(
                        document, DocumentStatus.PROCESSING, actor=context.actor
                    )
                )
                self.documents.add(document)
        try:
            result, report, security_issues = self._extract_document(document)
        except Exception as exc:
            return self.result_recorder.record_failure(
                document=document,
                job=job,
                context=context,
                error=exc,
                lease_token=lease_token,
            )
        self.result_recorder.record_success(
            document=document,
            job=job,
            context=context,
            result=result,
            report=report,
            security_issues=security_issues,
            lease_token=lease_token,
        )
        return document

    def _require_processable_job_status(self, job: ProcessingJob) -> None:
        if job.status not in {
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RETRYING,
            ProcessingJobStatus.RUNNING,
        }:
            raise InvalidStatusTransition(f"Cannot process job with status {job.status}")

    def _active_job_lease(
        self,
        job: ProcessingJob,
        claimed_lease_token: str | None,
    ) -> tuple[ProcessingJob, str]:
        if job.status == ProcessingJobStatus.RUNNING:
            if claimed_lease_token is None or job.lease_token != claimed_lease_token:
                raise LeaseLostError(f"Processing job is owned by another worker: {job.id}")
        else:
            with self.transactions.transaction():
                job = self.jobs.get(job.id)
                if job.status == ProcessingJobStatus.RUNNING:
                    raise LeaseLostError(f"Processing job is owned by another worker: {job.id}")
                job.start()
                self.jobs.save(job)
            claimed_lease_token = job.lease_token
        if claimed_lease_token is None:
            raise LeaseLostError(f"Processing job has no active lease: {job.id}")
        return job, claimed_lease_token

    def _extract_document(
        self,
        document: DocumentRecord,
    ) -> tuple[ExtractionResult, ValidationReport, tuple[ValidationIssue, ...]]:
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
        security_issues = validate_untrusted_extraction(
            result.extraction,
            parsed,
            result.provider_name,
        )
        if security_issues:
            report = ValidationReport(issues=(*report.issues, *security_issues))
        return result, report, security_issues

    def _document_source(self, document: DocumentRecord) -> DocumentSource:
        path: Path = self.storage.open_for_parser(document.storage_key)
        return DocumentSource(
            storage_key=document.storage_key,
            path=path,
            original_filename=document.original_filename,
            content_type=document.content_type,
        )


def _require_workspace(document: DocumentRecord, context: SecurityContext) -> None:
    if document.workspace_id != context.workspace_id:
        raise NotFoundError(f"Document not found: {document.id}")


def _require_owner_for_intake_role(document: DocumentRecord, context: SecurityContext) -> None:
    if is_intake_role(context) and document.submitted_by != context.user_id:
        raise NotFoundError(f"Document not found: {document.id}")
