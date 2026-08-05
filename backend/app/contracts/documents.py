from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.documents.jobs import ProcessingJob
from app.documents.models import AuditEvent, DocumentRecord


@runtime_checkable
class DocumentRepositoryPort(Protocol):
    def add(self, document: DocumentRecord) -> None: ...

    def get(self, document_id: UUID) -> DocumentRecord | None: ...

    def save(self, document: DocumentRecord) -> None: ...

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]: ...

    def reserve_identity(self, workspace_id: str, vendor: str, invoice_number: str) -> None: ...


@runtime_checkable
class AuditRepositoryPort(Protocol):
    def append(self, event: AuditEvent) -> None: ...

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]: ...


@runtime_checkable
class ProcessingJobRepositoryPort(Protocol):
    def add(self, job: ProcessingJob) -> None: ...

    def get(self, job_id: UUID) -> ProcessingJob | None: ...

    def save(self, job: ProcessingJob) -> None: ...

    def next_claimable(self) -> ProcessingJob | None: ...


@runtime_checkable
class TransactionManagerPort(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...
