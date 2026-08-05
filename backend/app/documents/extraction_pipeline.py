from __future__ import annotations

from pathlib import Path

from app.documents.models import DocumentRecord
from app.documents.repositories import DocumentRepository, ExtractionRepository
from app.providers.contracts import (
    DocumentSource,
    ExtractionResult,
    ExtractorProvider,
    ParserProvider,
    ProviderError,
)
from app.providers.storage import DocumentStorage
from app.validation.document import validate_document_invoice
from app.validation.invoice import ValidationIssue, ValidationReport
from app.validation.untrusted_content import validate_untrusted_extraction


class DocumentExtractionPipeline:
    def __init__(
        self,
        *,
        storage: DocumentStorage,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        parser: ParserProvider,
        extractor: ExtractorProvider,
    ) -> None:
        self.storage = storage
        self.documents = documents
        self.extractions = extractions
        self.parser = parser
        self.extractor = extractor

    def extract(
        self,
        document: DocumentRecord,
    ) -> tuple[ExtractionResult, ValidationReport, tuple[ValidationIssue, ...]]:
        parsed = self.parser.parse(self._source(document))
        if not parsed.text.strip():
            raise ProviderError("empty_document_text", provider_name=self.parser.provider_name)
        result = self.extractor.extract_invoice(parsed)
        report = validate_document_invoice(
            result.extraction.data,
            document,
            self.documents,
            self.extractions,
        )
        security_issues = validate_untrusted_extraction(
            result.extraction,
            parsed,
            result.provider_name,
        )
        if security_issues:
            report = ValidationReport(issues=(*report.issues, *security_issues))
        return result, report, security_issues

    def _source(self, document: DocumentRecord) -> DocumentSource:
        path: Path = self.storage.open_for_parser(document.storage_key)
        return DocumentSource(
            storage_key=document.storage_key,
            path=path,
            original_filename=document.original_filename,
            content_type=document.content_type,
        )
