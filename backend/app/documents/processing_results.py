from __future__ import annotations

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.jobs import ProcessingJob
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.processing_policy import ProcessingRetryPolicy
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
)
from app.documents.status import DocumentStatus
from app.documents.state_writer import DocumentStateWriter
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import ExtractionResult, ProviderError
from app.validation.invoice import ValidationIssue, ValidationReport


class ProcessingResultRecorder:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        extractions: ExtractionRepository,
        workflow: DocumentWorkflowService,
        retry_policy: ProcessingRetryPolicy,
        transactions: TransactionManager,
        state_writer: DocumentStateWriter | None = None,
    ) -> None:
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.extractions = extractions
        self.workflow = workflow
        self.retry_policy = retry_policy
        self.transactions = transactions
        self.state_writer = state_writer or DocumentStateWriter(
            documents,
            audits,
            workflow,
            transactions,
        )

    def record_success(
        self,
        *,
        document: DocumentRecord,
        job: ProcessingJob,
        context: SecurityContext,
        result: ExtractionResult,
        report: ValidationReport,
        security_issues: tuple[ValidationIssue, ...],
        lease_token: str,
    ) -> None:
        with self.transactions.transaction():
            if security_issues:
                self.audits.add(
                    AuditEvent(
                        document_id=document.id,
                        event_type="untrusted_content_flagged",
                        actor=context.actor,
                        old_status=document.status,
                        new_status=document.status,
                        payload_summary=(
                            "codes=" + ",".join(sorted({issue.code for issue in security_issues}))
                        ),
                    )
                )
            self.extractions.save(document.id, result, report)
            self.state_writer.transition(
                document,
                DocumentStatus.EXTRACTED,
                actor=context.actor,
            )
            self.state_writer.transition(
                document,
                DocumentStatus.NEEDS_REVIEW,
                actor=context.actor,
                payload_summary=(
                    "Validation requires reviewer correction."
                    if report.has_errors
                    else "Invoice is ready for reviewer approval."
                ),
            )
            job.provider_name = result.provider_name
            job.provider_trace_id = result.provider_trace_id
            job.succeed()
            self.jobs.save(job, expected_lease_token=lease_token)
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

    def record_failure(
        self,
        *,
        document: DocumentRecord,
        job: ProcessingJob,
        context: SecurityContext,
        error: Exception,
        lease_token: str,
    ) -> DocumentRecord:
        error_code = self.retry_policy.error_code(error)
        with self.transactions.transaction():
            if self.retry_policy.should_retry(error, job):
                job.retry(error_code, next_attempt_at=self.retry_policy.next_attempt_at(job))
                document.error_message = error_code
                self.state_writer.transition(
                    document,
                    DocumentStatus.QUEUED,
                    actor=context.actor,
                    payload_summary=error_code,
                )
            else:
                if isinstance(error, ProviderError) and error.retryable:
                    job.dead_letter(error_code)
                else:
                    job.fail(error_code)
                document.error_message = job.error_message
                if document.status != DocumentStatus.FAILED:
                    self.state_writer.transition(
                        document,
                        DocumentStatus.FAILED,
                        actor=context.actor,
                    )
                else:
                    self.documents.save(document)
            self.jobs.save(job, expected_lease_token=lease_token)
        log_operation(
            OperationEvent(
                event_type="processing_failed",
                workspace_id=context.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                job_id=str(job.id),
                status=job.status.value,
                error_code=error_code,
                retryable=isinstance(error, ProviderError) and error.retryable,
                attempt_count=job.attempt_count,
            )
        )
        return document
