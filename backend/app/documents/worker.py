from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.security import SecurityContext
from app.documents.models import DocumentRecord
from app.documents.repositories import JobRepository
from app.documents.services import DocumentProcessingService


class DocumentProcessingWorker:
    def __init__(
        self,
        jobs: JobRepository,
        processing_service: DocumentProcessingService,
        *,
        lease_seconds: int = 300,
    ) -> None:
        self.jobs = jobs
        self.processing_service = processing_service
        self.lease_seconds = max(1, lease_seconds)

    def run_once(self, context: SecurityContext) -> DocumentRecord | None:
        stale_before = datetime.now(UTC) - timedelta(seconds=self.lease_seconds)
        job = self.jobs.claim_next_processable(stale_before=stale_before)
        if job is None:
            return None
        return self.processing_service.process_job(job.id, context=context)
