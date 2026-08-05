from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.core.upload_scanning import build_upload_scanner
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.state_writer import DocumentStateWriter
from app.documents.worker import DocumentProcessingWorker
from app.documents.workflow import DocumentWorkflowService
from app.providers.contracts import ExtractorProvider, ParserProvider
from app.providers.factory import build_extractor_provider, build_parser_provider
from app.providers.storage import DocumentStorage, build_document_storage


@dataclass(frozen=True)
class DocumentModule:
    storage: DocumentStorage
    workflow: DocumentWorkflowService
    state_writer: DocumentStateWriter
    parser: ParserProvider
    extractor: ExtractorProvider
    upload_service: DocumentUploadService
    processing_service: DocumentProcessingService
    worker_service: DocumentProcessingWorker


def build_document_module(
    settings: Settings,
    persistence: PersistenceModule,
) -> DocumentModule:
    repositories = persistence.documents
    storage = _build_storage(settings)
    workflow = DocumentWorkflowService()
    state_writer = DocumentStateWriter(
        repositories.documents,
        repositories.audits,
        workflow,
        persistence.transactions,
    )
    parser = build_parser_provider(settings)
    extractor = build_extractor_provider(settings)
    upload_service = DocumentUploadService(
        storage,
        repositories.documents,
        repositories.jobs,
        repositories.audits,
        workflow,
        build_upload_scanner(settings),
        persistence.transactions,
        state_writer,
    )
    processing_service = DocumentProcessingService(
        storage,
        repositories.documents,
        repositories.jobs,
        repositories.audits,
        repositories.extractions,
        workflow,
        parser,
        extractor,
        max_processing_attempts=settings.max_processing_attempts,
        retry_base_seconds=settings.worker_retry_base_seconds,
        retry_max_seconds=settings.worker_retry_max_seconds,
        transactions=persistence.transactions,
        state_writer=state_writer,
    )
    worker_service = DocumentProcessingWorker(
        repositories.jobs,
        processing_service,
        lease_seconds=settings.worker_job_lease_seconds,
    )
    return DocumentModule(
        storage=storage,
        workflow=workflow,
        state_writer=state_writer,
        parser=parser,
        extractor=extractor,
        upload_service=upload_service,
        processing_service=processing_service,
        worker_service=worker_service,
    )


def _build_storage(settings: Settings) -> DocumentStorage:
    return build_document_storage(
        settings.document_storage_backend,
        Path(settings.upload_root),
        max_upload_bytes=settings.max_upload_bytes,
        s3_endpoint_url=settings.s3_endpoint_url or "",
        s3_bucket=settings.s3_bucket or "",
        s3_region=settings.s3_region or "auto",
        s3_access_key_id=settings.s3_access_key_id or "",
        s3_secret_access_key=settings.s3_secret_access_key or "",
    )
