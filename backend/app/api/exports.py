from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.http_headers import NO_STORE_HEADERS
from app.core.security import SecurityContext


router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/invoices.csv")
def export_invoices_csv(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    csv_text = container.export_service.export_approved_csv(context=context)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": 'attachment; filename="invoices.csv"',
        },
    )


@router.get("/predictions.json")
def export_predictions_json(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    json_text = container.export_service.export_predictions_json(context=context)
    return Response(
        content=json_text,
        media_type="application/json",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": 'attachment; filename="predictions.json"',
        },
    )
