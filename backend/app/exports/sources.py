from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.documents.models import DocumentRecord
from app.documents.repositories import DocumentRepository, ExtractionRepository, NotFoundError
from app.documents.status import DocumentStatus


@dataclass(frozen=True)
class ExportableInvoice:
    document_id: UUID
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None


class InvoiceExportSource(Protocol):
    def list_approved(self, workspace_id: str) -> list[ExportableInvoice]: ...

    def list_predictions(self, workspace_id: str) -> list[ExportableInvoice]: ...

    def get_many(self, document_ids: tuple[UUID, ...]) -> list[ExportableInvoice]: ...


class RepositoryInvoiceExportSource:
    """Adapt document persistence to the export module's read contract."""

    def __init__(
        self,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
    ) -> None:
        self.documents = documents
        self.extractions = extractions

    def list_approved(self, workspace_id: str) -> list[ExportableInvoice]:
        documents = self.documents.list_by_workspace_and_status(
            workspace_id,
            DocumentStatus.APPROVED,
        )
        return [self._project(document) for document in documents]

    def list_predictions(self, workspace_id: str) -> list[ExportableInvoice]:
        invoices: list[ExportableInvoice] = []
        for document in self.documents.list_by_workspace(workspace_id):
            try:
                invoices.append(self._project(document))
            except NotFoundError:
                continue
        return invoices

    def get_many(self, document_ids: tuple[UUID, ...]) -> list[ExportableInvoice]:
        return [self._project(self.documents.get(document_id)) for document_id in document_ids]

    def _project(self, document: DocumentRecord) -> ExportableInvoice:
        stored = self.extractions.get_for_document(document.id)
        data = stored.extraction_result.extraction.data
        return ExportableInvoice(
            document_id=document.id,
            vendor_name=data.vendor_name,
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            subtotal=data.subtotal,
            tax=data.tax,
            total=data.total,
            currency=data.currency,
        )
