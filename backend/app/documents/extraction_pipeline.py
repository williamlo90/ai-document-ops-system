from __future__ import annotations

from uuid import UUID

from app.bootstrap.persistence import PersistenceModule
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import InvoiceExtractionProvider
from app.providers.storage import PrivateDocumentStorage
from app.review.services import ReviewService
from app.validation.document import validate_for_review


class InvoiceExtractionPipeline:
    def __init__(self, *, persistence: PersistenceModule, storage: PrivateDocumentStorage, extractor: InvoiceExtractionProvider, reviews: ReviewService) -> None:
        self.persistence = persistence
        self.storage = storage
        self.extractor = extractor
        self.reviews = reviews
        self.workflow = DocumentWorkflowService()

    def process(self, document_id: UUID) -> None:
        document = self.persistence.documents.get(document_id)
        if document is None:
            raise KeyError(document_id)
        extraction = self.extractor.extract(self.storage.read(document.storage_key))
        validate_for_review(extraction.data)
        self.reviews.seed(document_id, extraction.data)
        for status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED, DocumentStatus.NEEDS_REVIEW):
            event = self.workflow.transition(document, status, "Mock extraction pipeline")
            with self.persistence.transactions.transaction():
                if self.persistence.documents.get(document.id) is None:
                    self.persistence.documents.add(document)
                else:
                    self.persistence.documents.save(document)
                self.persistence.audits.append(event)
