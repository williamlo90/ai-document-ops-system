from __future__ import annotations

from typing import Protocol

from app.extraction.schemas import InvoiceExtraction


class InvoiceExtractor(Protocol):
    def extract(self, content: bytes) -> InvoiceExtraction:
        """Return a proposal; this contract has no workflow authority."""
