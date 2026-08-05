from __future__ import annotations

from app.core.transactions import TransactionManager
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.repositories import JobRepository, LeaseLostError
from app.documents.status import InvalidStatusTransition


class JobLeaseService:
    def __init__(
        self,
        jobs: JobRepository,
        transactions: TransactionManager,
    ) -> None:
        self.jobs = jobs
        self.transactions = transactions

    def acquire(
        self,
        job: ProcessingJob,
        claimed_lease_token: str | None,
    ) -> tuple[ProcessingJob, str]:
        self.require_processable_status(job)
        if job.status == ProcessingJobStatus.RUNNING:
            if claimed_lease_token is None or job.lease_token != claimed_lease_token:
                raise LeaseLostError(f"Processing job is owned by another worker: {job.id}")
        else:
            with self.transactions.transaction():
                job = self.jobs.get(job.id)
                if job.status == ProcessingJobStatus.RUNNING:
                    raise LeaseLostError(f"Processing job is owned by another worker: {job.id}")
                job.start()
                self.jobs.save(job)
            claimed_lease_token = job.lease_token
        if claimed_lease_token is None:
            raise LeaseLostError(f"Processing job has no active lease: {job.id}")
        return job, claimed_lease_token

    def require_processable_status(self, job: ProcessingJob) -> None:
        if job.status not in {
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RETRYING,
            ProcessingJobStatus.RUNNING,
        }:
            raise InvalidStatusTransition(f"Cannot process job with status {job.status}")
