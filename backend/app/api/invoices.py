from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_container, require_context
from app.bootstrap.container import AppContainer
from app.core.security import SecurityContext
from app.invoices.queries import InvoiceQueries


router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", operation_id="listInvoices")
def list_invoices(context: SecurityContext = Depends(require_context), container: AppContainer = Depends(get_container)) -> dict[str, object]:
    return {"items": InvoiceQueries(container.persistence.documents).list_for_workspace(context.workspace_id)}
