from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.transactions import TransactionManager
from app.core.upload_scanning import UploadScanner
from app.documents.jobs import ProcessingJob
from app.documents.models import AuditEvent, DocumentRecord
from app.providers.storage import PrivateDocumentStorage


class DocumentAdder(Protocol):
    def add(self, document: DocumentRecord) -> None: ...


class AuditAppender(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class JobAdder(Protocol):
    def add(self, job: ProcessingJob) -> None: ...


@dataclass(frozen=True, slots=True)
class IntakeResult:
    document: DocumentRecord
    job: ProcessingJob
    audit: AuditEvent


class DocumentUploadService:
    def __init__(self, *, documents: DocumentAdder, audits: AuditAppender, jobs: JobAdder, transactions: TransactionManager, storage: PrivateDocumentStorage, scanner: UploadScanner, max_bytes: int) -> None:
        self.documents = documents
        self.audits = audits
        self.jobs = jobs
        self.transactions = transactions
        self.storage = storage
        self.scanner = scanner
        self.max_bytes = max_bytes

    def upload(self, content: bytes, *, filename: str, workspace_id: str, actor: str) -> IntakeResult:
        if not content or len(content) > self.max_bytes:
            raise ValueError("PDF size is outside the allowed range")
        self.scanner.scan(content)
        storage_key = self.storage.write(content)
        document = DocumentRecord(filename, storage_key, "application/pdf", workspace_id=workspace_id, submitted_by=actor, size_bytes=len(content))
        job = ProcessingJob(document_id=document.id)
        audit = AuditEvent(document.id, "document_uploaded", actor, new_status=document.status)
        try:
            with self.transactions.transaction():
                self.documents.add(document)
                self.audits.append(audit)
                self.jobs.add(job)
        except Exception:
            self.storage.delete(storage_key)
            raise
        return IntakeResult(document, job, audit)
