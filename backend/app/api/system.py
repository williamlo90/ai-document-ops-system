from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext
from app.system.dashboard import SystemDashboardService


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/dashboard")
def system_dashboard(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    service = SystemDashboardService(
        settings=container.settings,
        documents=container.documents,
        jobs=container.jobs,
        audits=container.audits,
        extractions=container.extractions,
        export_batches=container.export_batches,
    )
    return service.dashboard(context, readiness=container.readiness())
