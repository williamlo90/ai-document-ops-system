from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID

from app.core.security import SecurityContext
from app.documents.models import DocumentRecord
from app.documents.repositories import JobRepository, LeaseLostError
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
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=self.lease_seconds)
        job = self.jobs.claim_next_processable(stale_before=stale_before, now=now)
        if job is None:
            return None
        if job.lease_token is None:
            raise LeaseLostError(f"Claimed processing job has no lease token: {job.id}")
        heartbeat = _LeaseHeartbeat(
            jobs=self.jobs,
            job_id=job.id,
            lease_token=job.lease_token,
            interval_seconds=max(1.0, min(30.0, self.lease_seconds / 3)),
        )
        heartbeat.start()
        try:
            result = self.processing_service.process_job(
                job.id,
                context=context,
                lease_token=job.lease_token,
            )
            return result
        finally:
            heartbeat.stop()


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        jobs: JobRepository,
        job_id: UUID,
        lease_token: str,
        interval_seconds: float,
    ) -> None:
        self.jobs = jobs
        self.job_id = job_id
        self.lease_token = lease_token
        self.interval_seconds = interval_seconds
        self._stopping = Event()
        self._thread = Thread(target=self._run, name=f"job-heartbeat-{job_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=self.interval_seconds + 1)

    def _run(self) -> None:
        while not self._stopping.wait(self.interval_seconds):
            if not self.jobs.renew_lease(self.job_id, self.lease_token):
                return
