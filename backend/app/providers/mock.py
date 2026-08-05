from __future__ import annotations

from app.extraction.schemas import InvoiceExtraction
from app.review.datasets import sample_invoice


class MockInvoiceExtractor:
    name = "mock"

    def extract(self, pdf: bytes) -> InvoiceExtraction:
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Mock extractor requires PDF bytes")
        return InvoiceExtraction(data=sample_invoice())
