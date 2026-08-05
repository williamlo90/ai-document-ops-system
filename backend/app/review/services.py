from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.core.transactions import TransactionManager
from app.documents.models import AuditEvent
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService
from app.extraction.schemas import InvoiceData
from app.review.corrections import apply_correction
from app.review.models import CorrectionEvent, ReviewRecord
from app.validation.document import validate_for_review


class ApprovalBlocked(ValueError):
    pass


class DocumentRepository(Protocol):
    def get(self, document_id: UUID) -> DocumentRecord | None: ...
    def save(self, document: DocumentRecord) -> None: ...


class AuditRepository(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class ReviewRepository(Protocol):
    def save(self, record: ReviewRecord) -> None: ...
    def get(self, document_id: UUID) -> ReviewRecord | None: ...


class CorrectionRepository(Protocol):
    def append(self, event: CorrectionEvent) -> None: ...


class ReviewService:
    def __init__(self, *, documents: DocumentRepository, audits: AuditRepository, reviews: ReviewRepository, corrections: CorrectionRepository, transactions: TransactionManager) -> None:
        self.documents = documents
        self.audits = audits
        self.reviews = reviews
        self.corrections = corrections
        self.transactions = transactions
        self.workflow = DocumentWorkflowService()

    def seed(self, document_id: UUID, proposal: InvoiceData) -> ReviewRecord:
        record = ReviewRecord(document_id, proposal, proposal)
        with self.transactions.transaction():
            self.reviews.save(record)
        return record

    def correct(self, document_id: UUID, *, field_name: str, value: str | None, actor: str, reason: str) -> ReviewRecord:
        if not reason.strip():
            raise ValueError("Correction reason is required")
        record = self._required_record(document_id)
        before = getattr(record.current, field_name)
        current = apply_correction(record.current, field_name, value)
        validate_for_review(current)
        updated = ReviewRecord(record.document_id, record.original, current)
        with self.transactions.transaction():
            self.reviews.save(updated)
            self.corrections.append(CorrectionEvent(document_id, field_name, str(before) if before is not None else None, str(getattr(current, field_name)) if getattr(current, field_name) is not None else None, actor, reason))
        return updated

    def decide(self, document_id: UUID, *, approve: bool, actor: str, note: str) -> AuditEvent:
        if not note.strip():
            raise ValueError("Decision note is required")
        document = self.documents.get(document_id)
        if document is None:
            raise KeyError(document_id)
        record = self._required_record(document_id)
        report = validate_for_review(record.current)
        if approve and report.has_errors:
            raise ApprovalBlocked("Blocking validation issues must be corrected")
        target = DocumentStatus.APPROVED if approve else DocumentStatus.REJECTED
        event = self.workflow.transition(document, target, actor, note)
        with self.transactions.transaction():
            self.documents.save(document)
            self.audits.append(event)
        return event

    def _required_record(self, document_id: UUID) -> ReviewRecord:
        record = self.reviews.get(document_id)
        if record is None:
            raise KeyError(document_id)
        return record
