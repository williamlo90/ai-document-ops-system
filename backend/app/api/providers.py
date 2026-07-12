from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext
from app.documents.jobs import ProcessingJobStatus


router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/health")
def provider_health(
    _context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    jobs = container.jobs.list_all()
    failed = [
        job
        for job in jobs
        if job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTER}
    ]
    parser_name = container.processing_service.parser.provider_name
    extractor_name = container.processing_service.extractor.provider_name
    providers = [
        _provider_status("parser", parser_name, container.settings.parser_provider, jobs, failed),
        _provider_status(
            "extractor", extractor_name, container.settings.extractor_provider, jobs, failed
        ),
    ]
    overall = (
        "degraded"
        if any(provider["status"] == "degraded" for provider in providers)
        else (
            "ready_unverified"
            if any(provider["status"] == "ready_unverified" for provider in providers)
            else "healthy"
        )
    )
    return {"overall_status": overall, "providers": providers}


def _provider_status(
    role: str,
    runtime_name: str,
    configured_name: str,
    jobs: list,
    failed_jobs: list,
) -> dict[str, object]:
    is_mock = configured_name.strip().lower() == "mock"
    observed_jobs = [job for job in jobs if job.provider_name == runtime_name]
    observed_failures = [job for job in failed_jobs if job.provider_name == runtime_name]
    status = "degraded" if observed_failures else "healthy" if is_mock else "ready_unverified"
    return {
        "role": role,
        "provider_name": runtime_name,
        "configured_provider": configured_name,
        "status": status,
        "configuration_ready": True,
        "observed_runs": len(observed_jobs),
        "observed_failures": len(observed_failures),
        "evidence": (
            "Local deterministic provider is available."
            if is_mock
            else "Configuration loaded; health becomes verified after a real provider run."
        ),
    }
