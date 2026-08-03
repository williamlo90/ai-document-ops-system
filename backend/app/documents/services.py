from __future__ import annotations

from dataclasses import dataclass
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
from app.documents.extraction_pipeline import DocumentExtractionPipeline
from app.documents.job_leases import JobLeaseService
from app.documents.jobs import ProcessingJob
from app.documents.lifecycle_commands import DocumentLifecycleCommandService
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
from app.documents.state_writer import DocumentStateWriter
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import ExtractorProvider, ParserProvider
from app.providers.storage import DocumentStorage


@dataclass(frozen=True)
class UploadResult:
    document: DocumentRecord
    job: ProcessingJob


class UploadPersistenceError(RuntimeError):
    def __init__(
        self,
        *,
        storage_key: str,
        metadata_error: Exception,
        cleanup_error: Exception,
    ) -> None:
        super().__init__("Upload metadata failed and the stored object could not be removed")
        self.storage_key = storage_key
        self.metadata_error = metadata_error
        self.cleanup_error = cleanup_error


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
        state_writer: DocumentStateWriter | None = None,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.workflow = workflow
        self.upload_scanner = upload_scanner or SignatureUploadScanner()
        self.transactions = transactions or NoopTransactionManager()
        self.state_writer = state_writer or DocumentStateWriter(
            documents,
            audits,
            workflow,
            self.transactions,
        )

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
                self.state_writer.transition(
                    document,
                    DocumentStatus.QUEUED,
                    actor=context.actor,
                )
                job = self.jobs.add(ProcessingJob(document_id=document.id))
        except Exception as metadata_error:
            try:
                self.storage.delete(stored.storage_key)
            except Exception as cleanup_exc:
                raise UploadPersistenceError(
                    storage_key=stored.storage_key,
                    metadata_error=metadata_error,
                    cleanup_error=cleanup_exc,
                ) from metadata_error
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
        state_writer: DocumentStateWriter | None = None,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.extractions = extractions
        self.workflow = workflow
        self.max_processing_attempts = max_processing_attempts
        self.retry_base_seconds = max(1, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)
        self.transactions = transactions or NoopTransactionManager()
        self.state_writer = state_writer or DocumentStateWriter(
            documents,
            audits,
            workflow,
            self.transactions,
        )
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
            state_writer=self.state_writer,
        )
        self.extraction_pipeline = DocumentExtractionPipeline(
            storage=self.storage,
            documents=self.documents,
            extractions=self.extractions,
            parser=parser,
            extractor=extractor,
        )
        self.lifecycle_commands = DocumentLifecycleCommandService(
            documents=self.documents,
            jobs=self.jobs,
            state_writer=self.state_writer,
            transactions=self.transactions,
        )
        self.job_leases = JobLeaseService(self.jobs, self.transactions)

    @property
    def parser(self) -> ParserProvider:
        return self.extraction_pipeline.parser

    @parser.setter
    def parser(self, parser: ParserProvider) -> None:
        self.extraction_pipeline.parser = parser

    @property
    def extractor(self) -> ExtractorProvider:
        return self.extraction_pipeline.extractor

    @extractor.setter
    def extractor(self, extractor: ExtractorProvider) -> None:
        self.extraction_pipeline.extractor = extractor

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
        return self.lifecycle_commands.retry_failed(document_id, context)

    def reprocess_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        return self.lifecycle_commands.reprocess(document_id, context)

    def cancel_document(self, document_id: UUID, context: SecurityContext) -> DocumentRecord:
        return self.lifecycle_commands.cancel(document_id, context)

    def _process_job(
        self,
        job: ProcessingJob,
        context: SecurityContext,
        *,
        claimed_lease_token: str | None = None,
    ) -> DocumentRecord:
        document = self.documents.get(job.document_id)
        _require_workspace(document, context)
        self.job_leases.require_processable_status(job)
        if document.status not in {DocumentStatus.QUEUED, DocumentStatus.PROCESSING}:
            raise InvalidStatusTransition(f"Cannot process document with status {document.status}")
        job, lease_token = self.job_leases.acquire(job, claimed_lease_token)
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
            self.state_writer.transition(
                document,
                DocumentStatus.PROCESSING,
                actor=context.actor,
            )
        try:
            result, report, security_issues = self.extraction_pipeline.extract(document)
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


def _require_workspace(document: DocumentRecord, context: SecurityContext) -> None:
    if document.workspace_id != context.workspace_id:
        raise NotFoundError(f"Document not found: {document.id}")


def _require_owner_for_intake_role(document: DocumentRecord, context: SecurityContext) -> None:
    if is_intake_role(context) and document.submitted_by != context.user_id:
        raise NotFoundError(f"Document not found: {document.id}")
