from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext
from app.documents.jobs import ProcessingJobStatus
from app.providers.queries import ProviderActivity


router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/health")
def provider_health(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    parser_name = container.processing_service.parser.provider_name
    extractor_name = container.processing_service.extractor.provider_name
    if container.provider_health_queries is not None:
        activity = container.provider_health_queries.summary(context.workspace_id)
    else:
        document_ids = {
            document.id for document in container.documents.list_by_workspace(context.workspace_id)
        }
        jobs = [job for job in container.jobs.list_all() if job.document_id in document_ids]
        failed = [
            job
            for job in jobs
            if job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTER}
        ]
        activity = {
            name: ProviderActivity(
                observed_runs=sum(job.provider_name == name for job in jobs),
                observed_failures=sum(job.provider_name == name for job in failed),
            )
            for name in {parser_name, extractor_name}
        }
    providers = [
        _provider_status(
            "parser",
            parser_name,
            container.settings.parser_provider,
            activity.get(parser_name, ProviderActivity()),
        ),
        _provider_status(
            "extractor",
            extractor_name,
            container.settings.extractor_provider,
            activity.get(extractor_name, ProviderActivity()),
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
    activity: ProviderActivity,
) -> dict[str, object]:
    is_mock = configured_name.strip().lower() == "mock"
    status = (
        "degraded" if activity.observed_failures else "healthy" if is_mock else "ready_unverified"
    )
    return {
        "role": role,
        "provider_name": runtime_name,
        "configured_provider": configured_name,
        "status": status,
        "configuration_ready": True,
        "observed_runs": activity.observed_runs,
        "observed_failures": activity.observed_failures,
        "evidence": (
            "Local deterministic provider is available."
            if is_mock
            else "Configuration loaded; health becomes verified after a real provider run."
        ),
    }
