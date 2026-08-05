from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.core.upload_scanning import build_scanner
from app.documents.services import DocumentUploadService
from app.providers.storage import PrivateDocumentStorage


@dataclass(frozen=True, slots=True)
class DocumentModule:
    storage: PrivateDocumentStorage
    upload_service: DocumentUploadService


def build_document_module(settings: Settings, persistence: PersistenceModule) -> DocumentModule:
    storage = PrivateDocumentStorage(settings.upload_root)
    service = DocumentUploadService(
        documents=persistence.documents,
        audits=persistence.audits,
        jobs=persistence.jobs,
        transactions=persistence.transactions,
        storage=storage,
        scanner=build_scanner(settings.scanner_profile),
        max_bytes=settings.max_upload_bytes,
    )
    return DocumentModule(storage=storage, upload_service=service)
