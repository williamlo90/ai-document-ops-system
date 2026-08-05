from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_container, require_context
from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext
from app.documents.lifecycle_commands import cancel_job, retry_job


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/{job_id}/cancel", operation_id="cancelProcessingJob")
def cancel_processing_job(job_id: UUID, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, str]:
    job = container.persistence.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    cancel_job(job)
    with container.persistence.transactions.transaction():
        container.persistence.jobs.save(job)
    return {"status": job.status.value, "actor": context.actor}


@router.post("/{job_id}/retry", operation_id="retryProcessingJob")
def retry_processing_job(job_id: UUID, context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, str]:
    job = container.persistence.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    retry_job(job)
    with container.persistence.transactions.transaction():
        container.persistence.jobs.save(job)
    return {"status": job.status.value, "actor": context.actor}
