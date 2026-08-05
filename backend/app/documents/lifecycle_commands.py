from __future__ import annotations

from app.documents.jobs import JobStatus, ProcessingJob, StaleLeaseError


def cancel_job(job: ProcessingJob) -> None:
    if job.status == JobStatus.PROCESSING:
        raise StaleLeaseError("A leased job cannot be cancelled without fencing")
    job.status = JobStatus.CANCELLED


def retry_job(job: ProcessingJob) -> None:
    if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise ValueError("Only failed or cancelled jobs can be retried")
    job.status = JobStatus.RETRY
    job.error_code = None
