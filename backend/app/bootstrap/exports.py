from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.exports.batch_service import ExportBatchService
from app.exports.services import InvoiceExportService
from app.exports.sources import RepositoryInvoiceExportSource


@dataclass(frozen=True)
class ExportModule:
    service: InvoiceExportService
    batch_service: ExportBatchService


def build_export_module(
    settings: Settings,
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> ExportModule:
    repositories = persistence.documents
    source = RepositoryInvoiceExportSource(
        repositories.documents,
        repositories.extractions,
    )
    service = InvoiceExportService(
        source,
        documents.state_writer,
    )
    batch_service = ExportBatchService(
        settings=settings,
        repository=persistence.export_batches,
        documents=repositories.documents,
        extractions=repositories.extractions,
        audits=repositories.audits,
        workflow=documents.workflow,
        invoice_exports=service,
        transactions=persistence.transactions,
        state_writer=documents.state_writer,
    )
    return ExportModule(service=service, batch_service=batch_service)
