from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import AppContainer, get_container, require_review_context
from app.api.review import review_worklist_row
from app.core.security import SecurityContext
from app.overview.dashboard import OverviewDashboardService


router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/dashboard")
def overview_dashboard(
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    queue_rows = [
        review_worklist_row(document, context, container)
        for document in container.review_service.list_queue(context)
    ]
    export_workspace = (
        container.export_batch_service.workspace(
            context=context,
            view="ready",
            search="",
            vendor="",
            currency="",
            approved_by="",
            page=1,
            page_size=1,
            batch_id=None,
        )
        if context.is_admin
        else None
    )
    service = OverviewDashboardService(
        documents=container.documents,
        audits=container.audits,
        extractions=container.extractions,
        workflow_events=container.workflow_events,
    )
    return service.dashboard(
        context,
        queue_rows=queue_rows,
        export_workspace=export_workspace,
    )
