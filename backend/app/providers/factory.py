from __future__ import annotations

from app.providers.contracts import InvoiceExtractionProvider
from app.providers.mock import MockInvoiceExtractor


def build_extractor(name: str) -> InvoiceExtractionProvider:
    if name.strip().lower() == "mock":
        return MockInvoiceExtractor()
    raise ValueError("Only the credential-free mock provider is enabled in M08")
