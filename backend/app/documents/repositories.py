from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import AuditEvent, DocumentRecord, ReviewTask
from app.documents.status import DocumentStatus
from app.providers.contracts import ExtractionResult
from app.validation.invoice import ValidationReport


class NotFoundError(KeyError):
    pass


class LeaseLostError(RuntimeError):
    pass


class DocumentRepository(Protocol):
    def add(self, document: DocumentRecord) -> DocumentRecord: ...

    def get(self, document_id: UUID) -> DocumentRecord: ...

    def list_all(self) -> list[DocumentRecord]: ...

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]: ...

    def list_by_status(self, status: DocumentStatus) -> list[DocumentRecord]: ...

    def list_by_workspace_and_status(
        self, workspace_id: str, status: DocumentStatus
    ) -> list[DocumentRecord]: ...


class JobRepository(Protocol):
    def add(self, job: ProcessingJob) -> ProcessingJob: ...

    def save(
        self,
        job: ProcessingJob,
        *,
        expected_lease_token: str | None = None,
    ) -> ProcessingJob: ...

    def get(self, job_id: UUID) -> ProcessingJob: ...

    def get_latest_for_document(self, document_id: UUID) -> ProcessingJob: ...

    def list_all(self) -> list[ProcessingJob]: ...

    def list_by_status(self, status: ProcessingJobStatus) -> list[ProcessingJob]: ...

    def claim_next_processable(
        self,
        *,
        stale_before: datetime | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob | None: ...

    def renew_lease(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        renewed_at: datetime | None = None,
    ) -> bool: ...

    def count(self) -> int: ...


class AuditRepository(Protocol):
    def add(self, event: AuditEvent) -> AuditEvent: ...

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]: ...

    def count(self) -> int: ...


@dataclass(frozen=True)
class StoredExtraction:
    document_id: UUID
    extraction_result: ExtractionResult
    validation_report: ValidationReport


class ExtractionRepository(Protocol):
    def save(
        self,
        document_id: UUID,
        extraction_result: ExtractionResult,
        validation_report: ValidationReport,
    ) -> StoredExtraction: ...

    def get_for_document(self, document_id: UUID) -> StoredExtraction: ...

    def get_for_documents(self, document_ids: list[UUID]) -> dict[UUID, StoredExtraction]: ...

    def find_by_invoice_identity(
        self,
        vendor_identity: str,
        invoice_identity: str,
    ) -> list[UUID]: ...


class ReviewTaskRepository(Protocol):
    def save(self, task: ReviewTask) -> ReviewTask: ...

    def get_for_document(self, document_id: UUID) -> ReviewTask: ...

    def list_open(self) -> list[ReviewTask]: ...


@dataclass
class InMemoryDocumentRepository:
    records: dict[UUID, DocumentRecord] = field(default_factory=dict)

    def add(self, document: DocumentRecord) -> DocumentRecord:
        self.records[document.id] = document
        return document

    def get(self, document_id: UUID) -> DocumentRecord:
        try:
            return self.records[document_id]
        except KeyError as exc:
            raise NotFoundError(f"Document not found: {document_id}") from exc

    def list_all(self) -> list[DocumentRecord]:
        return list(self.records.values())

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        return [
            document for document in self.records.values() if document.workspace_id == workspace_id
        ]

    def list_by_status(self, status: DocumentStatus) -> list[DocumentRecord]:
        return [document for document in self.records.values() if document.status == status]

    def list_by_workspace_and_status(
        self, workspace_id: str, status: DocumentStatus
    ) -> list[DocumentRecord]:
        return [
            document
            for document in self.records.values()
            if document.workspace_id == workspace_id and document.status == status
        ]


@dataclass
class InMemoryJobRepository:
    records: dict[UUID, ProcessingJob] = field(default_factory=dict)

    def add(self, job: ProcessingJob) -> ProcessingJob:
        self.records[job.id] = job
        return job

    def save(
        self,
        job: ProcessingJob,
        *,
        expected_lease_token: str | None = None,
    ) -> ProcessingJob:
        current = self.records.get(job.id)
        if (
            expected_lease_token is None
            and current is not None
            and current.status == ProcessingJobStatus.RUNNING
            and current.lease_token is not None
        ):
            if job.status == ProcessingJobStatus.RUNNING and job.lease_token == current.lease_token:
                expected_lease_token = current.lease_token
            else:
                raise LeaseLostError(f"Processing job lease token is required to update: {job.id}")
        if expected_lease_token is not None and (
            current is None or current.lease_token != expected_lease_token
        ):
            raise LeaseLostError(f"Processing job lease was lost: {job.id}")
        if current is None:
            self.records[job.id] = job
            return job
        current.__dict__.update(deepcopy(job.__dict__))
        return current

    def get(self, job_id: UUID) -> ProcessingJob:
        try:
            return deepcopy(self.records[job_id])
        except KeyError as exc:
            raise NotFoundError(f"Processing job not found: {job_id}") from exc

    def get_latest_for_document(self, document_id: UUID) -> ProcessingJob:
        matches = [job for job in self.records.values() if job.document_id == document_id]
        if not matches:
            raise NotFoundError(f"Processing job not found for document: {document_id}")
        return deepcopy(max(matches, key=lambda job: job.created_at))

    def list_all(self) -> list[ProcessingJob]:
        return deepcopy(list(self.records.values()))

    def list_by_status(self, status: ProcessingJobStatus) -> list[ProcessingJob]:
        return deepcopy([job for job in self.records.values() if job.status == status])

    def claim_next_processable(
        self,
        *,
        stale_before: datetime | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob | None:
        current = now or datetime.now(UTC)
        candidates = [
            job
            for job in self.records.values()
            if job.status == ProcessingJobStatus.QUEUED
            or (
                job.status == ProcessingJobStatus.RETRYING
                and (job.next_attempt_at is None or job.next_attempt_at <= current)
            )
            or (
                stale_before is not None
                and job.status == ProcessingJobStatus.RUNNING
                and job.updated_at <= stale_before
            )
        ]
        if not candidates:
            return None
        job = min(
            candidates,
            key=lambda candidate: (
                candidate.status != ProcessingJobStatus.RUNNING,
                candidate.created_at,
            ),
        )
        if job.status == ProcessingJobStatus.RUNNING:
            job.retry("worker_lease_expired")
        job.start()
        return deepcopy(job)

    def renew_lease(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        renewed_at: datetime | None = None,
    ) -> bool:
        job = self.records.get(job_id)
        if (
            job is None
            or job.status != ProcessingJobStatus.RUNNING
            or job.lease_token != lease_token
        ):
            return False
        job.updated_at = renewed_at or datetime.now(UTC)
        return True

    def count(self) -> int:
        return len(self.records)


@dataclass
class InMemoryAuditRepository:
    records: list[AuditEvent] = field(default_factory=list)

    def add(self, event: AuditEvent) -> AuditEvent:
        self.records.append(event)
        return event

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]:
        return [event for event in self.records if event.document_id == document_id]

    def count(self) -> int:
        return len(self.records)


@dataclass
class InMemoryExtractionRepository:
    records: dict[UUID, StoredExtraction] = field(default_factory=dict)

    def save(
        self,
        document_id: UUID,
        extraction_result: ExtractionResult,
        validation_report: ValidationReport,
    ) -> StoredExtraction:
        stored = StoredExtraction(
            document_id=document_id,
            extraction_result=extraction_result,
            validation_report=validation_report,
        )
        self.records[document_id] = stored
        return stored

    def get_for_document(self, document_id: UUID) -> StoredExtraction:
        try:
            return self.records[document_id]
        except KeyError as exc:
            raise NotFoundError(f"Extraction not found for document: {document_id}") from exc

    def get_for_documents(self, document_ids: list[UUID]) -> dict[UUID, StoredExtraction]:
        return {
            document_id: self.records[document_id]
            for document_id in document_ids
            if document_id in self.records
        }

    def find_by_invoice_identity(
        self,
        vendor_identity: str,
        invoice_identity: str,
    ) -> list[UUID]:
        return [
            document_id
            for document_id, stored in self.records.items()
            if _identity_text(stored.extraction_result.extraction.data.vendor_name)
            == vendor_identity
            and _identity_text(stored.extraction_result.extraction.data.invoice_number)
            == invoice_identity
        ]


@dataclass
class InMemoryReviewTaskRepository:
    records: dict[UUID, ReviewTask] = field(default_factory=dict)

    def save(self, task: ReviewTask) -> ReviewTask:
        self.records[task.document_id] = task
        return task

    def get_for_document(self, document_id: UUID) -> ReviewTask:
        try:
            return self.records[document_id]
        except KeyError as exc:
            raise NotFoundError(f"Review task not found for document: {document_id}") from exc

    def list_open(self) -> list[ReviewTask]:
        return [task for task in self.records.values() if task.status == "open"]


def _identity_text(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())
