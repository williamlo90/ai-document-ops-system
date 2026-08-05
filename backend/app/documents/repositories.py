from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from typing import Iterator
from uuid import UUID

from app.documents.models import AuditEvent, DocumentRecord
from app.documents.jobs import ProcessingJob


class DuplicateInvoiceIdentity(ValueError):
    pass


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[UUID, DocumentRecord] = {}
        self._identities: set[tuple[str, str, str]] = set()

    def add(self, document: DocumentRecord) -> None:
        self._documents[document.id] = deepcopy(document)

    def get(self, document_id: UUID) -> DocumentRecord | None:
        document = self._documents.get(document_id)
        return deepcopy(document) if document is not None else None

    def save(self, document: DocumentRecord) -> None:
        if document.id not in self._documents:
            raise KeyError(document.id)
        self._documents[document.id] = deepcopy(document)

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        return [deepcopy(item) for item in self._documents.values() if item.workspace_id == workspace_id]

    def reserve_identity(self, workspace_id: str, vendor: str, invoice_number: str) -> None:
        identity = (workspace_id, vendor.casefold(), invoice_number.casefold())
        if identity in self._identities:
            raise DuplicateInvoiceIdentity(invoice_number)
        self._identities.add(identity)

    def snapshot_state(self) -> tuple[dict[UUID, DocumentRecord], set[tuple[str, str, str]]]:
        return deepcopy(self._documents), set(self._identities)

    def restore_state(self, state: tuple[dict[UUID, DocumentRecord], set[tuple[str, str, str]]]) -> None:
        self._documents, self._identities = deepcopy(state[0]), set(state[1])


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(deepcopy(event))

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]:
        return [deepcopy(event) for event in self._events if event.document_id == document_id]

    def snapshot_state(self) -> list[AuditEvent]:
        return deepcopy(self._events)

    def restore_state(self, state: list[AuditEvent]) -> None:
        self._events = deepcopy(state)


class InMemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, ProcessingJob] = {}

    def add(self, job: ProcessingJob) -> None:
        self._jobs[job.id] = deepcopy(job)

    def get(self, job_id: UUID) -> ProcessingJob | None:
        job = self._jobs.get(job_id)
        return deepcopy(job) if job is not None else None

    def save(self, job: ProcessingJob) -> None:
        if job.id not in self._jobs:
            raise KeyError(job.id)
        self._jobs[job.id] = deepcopy(job)

    def next_claimable(self) -> ProcessingJob | None:
        for job in self._jobs.values():
            if job.status.value in {"queued", "retry"}:
                return deepcopy(job)
        return None

    def snapshot_state(self) -> dict[UUID, ProcessingJob]:
        return deepcopy(self._jobs)

    def restore_state(self, state: dict[UUID, ProcessingJob]) -> None:
        self._jobs = deepcopy(state)


class InMemoryTransactionManager:
    def __init__(self, documents: InMemoryDocumentRepository, audits: InMemoryAuditRepository, jobs: InMemoryJobRepository | None = None) -> None:
        self.documents = documents
        self.audits = audits
        self.jobs = jobs
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            document_state = self.documents.snapshot_state()
            audit_state = self.audits.snapshot_state()
            job_state = self.jobs.snapshot_state() if self.jobs is not None else None
            try:
                yield
            except Exception:
                self.documents.restore_state(document_state)
                self.audits.restore_state(audit_state)
                if self.jobs is not None and job_state is not None:
                    self.jobs.restore_state(job_state)
                raise
