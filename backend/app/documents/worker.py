from __future__ import annotations

from app.core.security import SecurityContext
from app.documents.models import DocumentRecord
from app.documents.repositories import JobRepository
from app.documents.services import DocumentProcessingService


class DocumentProcessingWorker:
    def __init__(
        self,
        jobs: JobRepository,
        processing_service: DocumentProcessingService,
    ) -> None:
        self.jobs = jobs
        self.processing_service = processing_service

    def run_once(self, context: SecurityContext) -> DocumentRecord | None:
        job = self.jobs.claim_next_processable()
        if job is None:
            return None
        return self.processing_service.process_job(job.id, context=context)
