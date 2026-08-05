from __future__ import annotations

from typing import Protocol

from app.extraction.schemas import InvoiceExtraction


class InvoiceExtractionProvider(Protocol):
    name: str
    def extract(self, pdf: bytes) -> InvoiceExtraction: ...


class ProviderFailure(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
