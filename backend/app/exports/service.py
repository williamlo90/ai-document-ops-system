from __future__ import annotations

from hashlib import sha256
from typing import Protocol
from uuid import UUID

from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.exports.csv_renderer import render_invoice_csv
from app.exports.models import ExportRecord
from app.exports.repositories import IdempotencyConflict
from app.review.models import ReviewRecord


class ExportNotAllowed(ValueError):
    pass


class DocumentReader(Protocol):
    def get(self, document_id: UUID) -> DocumentRecord | None: ...


class ReviewReader(Protocol):
    def get(self, document_id: UUID) -> ReviewRecord | None: ...


class ExportLedger(Protocol):
    def get_by_idempotency_key(self, key: str) -> ExportRecord | None: ...
    def record_success(self, record: ExportRecord) -> ExportRecord: ...


class InvoiceExportService:
    def __init__(
        self,
        *,
        documents: DocumentReader,
        reviews: ReviewReader,
        exports: ExportLedger,
    ) -> None:
        self.documents = documents
        self.reviews = reviews
        self.exports = exports

    def export_csv(
        self,
        document_id: UUID,
        *,
        idempotency_key: str,
        actor: str,
    ) -> ExportRecord:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise ValueError("Idempotency key must contain 1 to 128 characters")
        if not actor.strip():
            raise ValueError("Export actor is required")

        existing = self.exports.get_by_idempotency_key(key)
        if existing is not None:
            if existing.document_id != document_id:
                raise IdempotencyConflict(
                    "Idempotency key is already associated with another invoice"
                )
            return existing

        document = self.documents.get(document_id)
        if document is None:
            raise KeyError(document_id)
        if document.status is not DocumentStatus.APPROVED:
            raise ExportNotAllowed("Only approved invoices can be exported")

        review = self.reviews.get(document_id)
        if review is None:
            raise KeyError(f"No reviewed invoice data for {document_id}")

        content = render_invoice_csv(document_id, review.current)
        record = ExportRecord(
            document_id=document_id,
            workspace_id=document.workspace_id,
            idempotency_key=key,
            requested_by=actor.strip(),
            filename=f"invoice-{document_id}.csv",
            content=content,
            content_sha256=sha256(content).hexdigest(),
        )
        return self.exports.record_success(record)

