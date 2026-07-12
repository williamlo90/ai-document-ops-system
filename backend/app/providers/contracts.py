from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.extraction.schemas import InvoiceExtraction


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    pages: tuple[ParsedPage, ...] = field(default_factory=tuple)
    provider_name: str = "unknown"
    provider_trace_id: str | None = None


@dataclass(frozen=True)
class DocumentSource:
    storage_key: str
    path: Path
    original_filename: str
    content_type: str


@dataclass(frozen=True)
class ExtractionResult:
    extraction: InvoiceExtraction
    provider_name: str
    provider_trace_id: str | None = None


class ProviderError(RuntimeError):
    def __init__(self, message: str, provider_name: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider_name = provider_name
        self.retryable = retryable


class ParserProvider(Protocol):
    provider_name: str

    def parse(self, source: DocumentSource) -> ParsedDocument: ...


class ExtractorProvider(Protocol):
    provider_name: str

    def extract_invoice(self, parsed_document: ParsedDocument) -> ExtractionResult: ...
