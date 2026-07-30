from __future__ import annotations

import csv
import json
from io import StringIO
from uuid import uuid4

from app.core.security import SecurityContext, require_admin
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
)
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService
from app.exports.csv_security import escape_spreadsheet_formula


INVOICE_CSV_HEADERS = [
    "document_id",
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
]


class InvoiceExportService:
    def __init__(
        self,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        transactions: TransactionManager | None = None,
    ) -> None:
        self.documents = documents
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow
        self.transactions = transactions or NoopTransactionManager()

    def export_approved_csv(self, context: SecurityContext) -> str:
        require_admin(context)
        export_id = str(uuid4())
        approved_documents = self.documents.list_by_workspace_and_status(
            context.workspace_id, DocumentStatus.APPROVED
        )
        csv_text = self.render_documents_csv(approved_documents)
        with self.transactions.transaction():
            for document in approved_documents:
                self.audits.add(
                    self.workflow.transition(
                        document,
                        DocumentStatus.EXPORTED,
                        context.actor,
                        payload_summary=f"export_id={export_id}",
                    )
                )
                self.documents.add(document)
        return csv_text

    def render_documents_csv(self, documents: list[DocumentRecord]) -> str:
        rows = [self._row_for_document(document) for document in documents]
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=INVOICE_CSV_HEADERS, lineterminator="\n")
        writer.writeheader()
        for _document, row in rows:
            writer.writerow({key: escape_spreadsheet_formula(value) for key, value in row.items()})
        return output.getvalue()

    def export_predictions_json(self, context: SecurityContext) -> str:
        require_admin(context)
        rows = []
        for document in self.documents.list_by_workspace(context.workspace_id):
            try:
                _document, row = self._row_for_document(document)
            except NotFoundError:
                continue
            rows.append(
                {key: str(value) if value is not None else None for key, value in row.items()}
            )
        rows.sort(key=lambda row: row["document_id"] or "")
        return json.dumps(rows, indent=2)

    def _row_for_document(
        self, document: DocumentRecord
    ) -> tuple[DocumentRecord, dict[str, object]]:
        stored = self.extractions.get_for_document(document.id)
        data = stored.extraction_result.extraction.data
        row: dict[str, object] = {
            "document_id": str(document.id),
            "vendor_name": data.vendor_name,
            "invoice_number": data.invoice_number,
            "invoice_date": data.invoice_date.isoformat() if data.invoice_date else None,
            "due_date": data.due_date.isoformat() if data.due_date else None,
            "subtotal": data.subtotal,
            "tax": data.tax,
            "total": data.total,
            "currency": data.currency,
        }
        return document, row
