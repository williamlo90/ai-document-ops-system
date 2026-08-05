from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
def metrics_summary(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return container.metrics_service.summary(context)
