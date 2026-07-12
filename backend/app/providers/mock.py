from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extraction.schemas import FieldConfidence, InvoiceData, InvoiceExtraction
from app.providers.contracts import DocumentSource, ExtractionResult, ParsedDocument, ParsedPage


class MockParserProvider:
    provider_name = "mock_parser"

    def __init__(self, text: str = "mock invoice text") -> None:
        self.text = text

    def parse(self, source: DocumentSource) -> ParsedDocument:
        return ParsedDocument(
            text=self.text,
            pages=(ParsedPage(page_number=1, text=self.text),),
            provider_name=self.provider_name,
            provider_trace_id=source.storage_key,
        )


class MockInvoiceExtractor:
    provider_name = "mock_extractor"

    def __init__(self, invoice_data: InvoiceData | None = None) -> None:
        self.invoice_data = invoice_data or InvoiceData(
            vendor_name="Acme Logistics",
            invoice_number="INV-001",
            invoice_date=date(2026, 6, 18),
            due_date=date(2026, 7, 18),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            total=Decimal("110.00"),
            currency="USD",
        )

    def extract_invoice(self, parsed_document: ParsedDocument) -> ExtractionResult:
        extraction = InvoiceExtraction(
            data=self.invoice_data,
            confidence=(
                FieldConfidence("invoice_number", Decimal("0.99"), source_page=1),
                FieldConfidence("total", Decimal("0.99"), source_page=1),
            ),
        )
        return ExtractionResult(
            extraction=extraction,
            provider_name=self.provider_name,
            provider_trace_id=parsed_document.provider_trace_id,
        )
