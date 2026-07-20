from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext
from app.evaluation.dashboard import EvaluationRunIncomplete


router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/dashboard")
def evaluation_dashboard(
    run: str | None = None,
    range_limit: int = Query(default=10, ge=1, le=20),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return container.evaluation_dashboard.dashboard(
        context=context,
        run_id=run,
        range_limit=range_limit,
    )


@router.get("/preflight")
def evaluation_preflight(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return {"preflight": container.evaluation_dashboard.preflight(context)}


@router.post("/runs")
def run_evaluation(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.evaluation_dashboard.run(context=context)
    except EvaluationRunIncomplete as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": str(exc),
                "attempt": container.evaluation_dashboard.attempt_response(exc.attempt),
            },
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
