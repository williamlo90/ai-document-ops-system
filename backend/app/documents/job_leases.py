from __future__ import annotations

from app.documents.jobs import ProcessingJob


def claim_job(job: ProcessingJob, lease_seconds: int = 60) -> str:
    return job.claim(lease_seconds)


def heartbeat_job(job: ProcessingJob, token: str, lease_seconds: int = 60) -> None:
    job.heartbeat(token, lease_seconds)
