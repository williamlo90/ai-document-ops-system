from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from uuid import UUID

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext
from app.documents.jobs import ProcessingJob
from app.documents.processing_queue import ProcessingMessage, ProcessingQueue, QueueDisposition
from app.documents.models import DocumentRecord
from app.documents.repositories import JobRepository, LeaseLostError, NotFoundError
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
        return self._run_claimed(job, context)

    def run_job(self, job_id: UUID, context: SecurityContext) -> DocumentRecord | None:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=self.lease_seconds)
        job = self.jobs.claim_processable(
            job_id,
            stale_before=stale_before,
            now=now,
        )
        return self._run_claimed(job, context)

    def _run_claimed(
        self,
        job: ProcessingJob | None,
        context: SecurityContext,
    ) -> DocumentRecord | None:
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


class QueueProcessingWorker:
    def __init__(
        self,
        queue: ProcessingQueue,
        jobs: JobRepository,
        worker: DocumentProcessingWorker,
        *,
        max_delivery_count: int = 5,
    ) -> None:
        self.queue = queue
        self.jobs = jobs
        self.worker = worker
        self.max_delivery_count = max(1, max_delivery_count)

    def run_once(self, *, max_wait_seconds: float = 1.0) -> bool:
        return self.queue.receive_one(self._handle, max_wait_seconds=max_wait_seconds)

    def _handle(
        self,
        message: ProcessingMessage,
        delivery_count: int,
    ) -> QueueDisposition:
        try:
            job = self.jobs.get(message.job_id)
            if job.document_id != message.document_id:
                self._log(message, "queue_message_dead_lettered", "identity_mismatch")
                return QueueDisposition.DEAD_LETTER
            result = self.worker.run_job(
                message.job_id,
                SecurityContext(
                    actor="service-bus-worker",
                    is_admin=True,
                    workspace_id=message.workspace_id,
                    user_id="service-bus-worker",
                    role="admin",
                    trace_id=message.trace_id,
                ),
            )
            # A terminal, future-retry, or actively leased job is a safe duplicate.
            # PostgreSQL polling remains the recovery path for future retries.
            del result
            self._log(message, "queue_message_completed")
            return QueueDisposition.COMPLETE
        except NotFoundError:
            self._log(message, "queue_message_dead_lettered", "job_not_found")
            return QueueDisposition.DEAD_LETTER
        except LeaseLostError:
            self._log(message, "queue_duplicate_completed", "lease_owned_elsewhere")
            return QueueDisposition.COMPLETE
        except Exception:
            if delivery_count >= self.max_delivery_count:
                self._log(message, "queue_message_dead_lettered", "worker_error")
                return QueueDisposition.DEAD_LETTER
            self._log(message, "queue_message_abandoned", "worker_error")
            return QueueDisposition.ABANDON

    @staticmethod
    def _log(
        message: ProcessingMessage,
        event_type: str,
        error_code: str | None = None,
    ) -> None:
        log_operation(
            OperationEvent(
                event_type=event_type,
                workspace_id=message.workspace_id,
                actor="service-bus-worker",
                document_id=str(message.document_id),
                job_id=str(message.job_id),
                error_code=error_code,
                trace_id=message.trace_id,
            )
        )


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
