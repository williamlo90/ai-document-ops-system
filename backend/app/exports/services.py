from __future__ import annotations

import csv
import json
from io import StringIO
from uuid import UUID, uuid4

from app.core.security import SecurityContext, require_admin
from app.documents.state_writer import DocumentStateWriter
from app.documents.status import DocumentStatus
from app.exports.csv_security import escape_spreadsheet_formula
from app.exports.sources import ExportableInvoice, InvoiceExportSource


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
        source: InvoiceExportSource,
        state_writer: DocumentStateWriter,
    ) -> None:
        self.source = source
        self.state_writer = state_writer

    def export_approved_csv(self, context: SecurityContext) -> str:
        """Render the local download path and record the resulting export state."""

        require_admin(context)
        export_id = str(uuid4())
        approved_invoices = self.source.list_approved(context.workspace_id)
        csv_text = self.render_invoices_csv(approved_invoices)
        self.state_writer.transition_many_by_id(
            tuple(invoice.document_id for invoice in approved_invoices),
            context.workspace_id,
            DocumentStatus.EXPORTED,
            context.actor,
            payload_summary=f"export_id={export_id}; mode=direct_download",
        )
        return csv_text

    def render_invoices_csv(self, invoices: list[ExportableInvoice]) -> str:
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=INVOICE_CSV_HEADERS, lineterminator="\n")
        writer.writeheader()
        for invoice in invoices:
            row = self._row_for_invoice(invoice)
            writer.writerow({key: escape_spreadsheet_formula(value) for key, value in row.items()})
        return output.getvalue()

    def render_document_ids_csv(self, document_ids: tuple[UUID, ...]) -> str:
        return self.render_invoices_csv(self.source.get_many(document_ids))

    def export_predictions_json(self, context: SecurityContext) -> str:
        require_admin(context)
        rows = [
            {
                key: str(value) if value is not None else None
                for key, value in self._row_for_invoice(invoice).items()
            }
            for invoice in self.source.list_predictions(context.workspace_id)
        ]
        rows.sort(key=lambda row: row["document_id"] or "")
        return json.dumps(rows, indent=2)

    @staticmethod
    def _row_for_invoice(invoice: ExportableInvoice) -> dict[str, object]:
        return {
            "document_id": str(invoice.document_id),
            "vendor_name": invoice.vendor_name,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax,
            "total": invoice.total,
            "currency": invoice.currency,
        }
