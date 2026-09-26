from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.serializers import document_response
from app.core.security import SecurityContext
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition
from app.integrations.models import (
    IntegrationDeliveryError,
    IntegrationIdempotencyConflict,
    IntegrationOutcomeUnknown,
)
from app.integrations.projections import erp_delivery_projection


router = APIRouter(prefix="/integrations", tags=["integrations"])


class ReconcileDeliveryRequest(BaseModel):
    succeeded: bool
    external_id: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


@router.get("/status")
def integration_status(
    _context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    settings = container.settings
    integrations = [
        _status(
            "email",
            settings.email_provider,
            settings.email_provider == "mock" or bool(settings.resend_api_key),
            settings.email_sandbox_mode,
            (
                "Sandbox recipient is enforced."
                if settings.email_sandbox_mode
                else "Live delivery enabled."
            ),
        ),
        _status(
            "accounting",
            settings.accounting_provider,
            settings.accounting_provider in {"csv_download", "mock"}
            or (
                settings.accounting_provider == "erpnext"
                and bool(settings.erpnext_api_key)
                and bool(settings.erpnext_api_secret)
            ),
            settings.accounting_sandbox_mode,
            (
                "Approved invoices can create verified ERPNext drafts."
                if settings.accounting_provider == "erpnext"
                else "Approved invoices can be downloaded through the audited CSV export contract."
            ),
        ),
        _status(
            "document_storage",
            settings.document_storage_backend,
            settings.document_storage_backend == "local"
            or (
                settings.document_storage_backend in {"azure", "azure-blob", "azure_blob"}
                and bool(settings.azure_storage_container)
                and bool(
                    settings.azure_storage_account_url or settings.azure_storage_connection_string
                )
            )
            or all(
                (
                    settings.s3_endpoint_url,
                    settings.s3_bucket,
                    settings.s3_access_key_id,
                    settings.s3_secret_access_key,
                )
            ),
            settings.document_storage_backend == "local"
            or bool(settings.azure_storage_connection_string),
            (
                "Private local storage."
                if settings.document_storage_backend == "local"
                else (
                    "Private Azure Blob storage configured."
                    if settings.document_storage_backend in {"azure", "azure-blob", "azure_blob"}
                    else "S3-compatible credentials loaded."
                )
            ),
        ),
        _status(
            "database",
            settings.storage_backend,
            settings.storage_backend in {"memory", "sqlite"} or bool(settings.database_url),
            settings.storage_backend != "postgres",
            (
                "Local persistence."
                if settings.storage_backend != "postgres"
                else "PostgreSQL connection configured."
            ),
        ),
        _status(
            "processing_queue",
            settings.processing_queue_backend,
            settings.processing_queue_backend in {"", "none", "polling", "memory"}
            or (
                settings.processing_queue_backend
                in {"azure", "azure-service-bus", "azure_service_bus", "service-bus"}
                and bool(settings.azure_service_bus_queue_name)
                and bool(
                    settings.azure_service_bus_namespace
                    or settings.azure_service_bus_connection_string
                )
            ),
            settings.processing_queue_backend in {"", "none", "polling", "memory"}
            or bool(settings.azure_service_bus_connection_string),
            (
                "Database polling fallback is active."
                if settings.processing_queue_backend in {"", "none", "polling"}
                else "Azure Service Bus wake-up queue configured; PostgreSQL remains authoritative."
            ),
        ),
    ]
    return {"integrations": integrations}


@router.post("/{integration_name}/test")
def test_integration(
    integration_name: str,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    statuses = integration_status(context, container)["integrations"]
    match = next(
        (item for item in statuses if item["name"] == integration_name),
        None,
    )
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {
        "integration": {
            **match,
            "test_status": "passed" if match["configuration_ready"] else "failed",
        }
    }


def _status(
    name: str, provider: str, ready: bool, sandbox: bool, evidence: str
) -> dict[str, object]:
    return {
        "name": name,
        "provider": provider,
        "status": "healthy" if ready else "not_configured",
        "configuration_ready": ready,
        "sandbox_mode": sandbox,
        "evidence": evidence,
    }


@router.post("/accounting/documents/{document_id}/export")
def export_document_to_accounting(
    document_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    if idempotency_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key header is required",
        )
    try:
        result = container.integration_service.send_approved_invoice(
            document_id,
            context,
            idempotency_key=idempotency_key,
        )
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (IntegrationIdempotencyConflict, IntegrationOutcomeUnknown) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except IntegrationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Integration delivery failed",
                "code": exc.code,
                "retryable": exc.retryable,
                "outcome_unknown": exc.outcome_unknown,
            },
        ) from exc
    return {
        "document": document_response(result.document),
        "integration": {
            "adapter_name": result.integration_result.adapter_name,
            "external_id": result.integration_result.external_id,
            "status": result.integration_result.status,
            "retryable": result.integration_result.retryable,
            "external_url": result.integration_result.external_url,
            "provider_docstatus": result.integration_result.provider_docstatus,
            "delivery_status": result.delivery.status.value,
            "attempt_count": result.delivery.attempt_count,
            "replayed": result.replayed,
        },
    }


@router.get("/erpnext/documents/{document_id}/delivery")
def erpnext_delivery(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _require_erpnext(container)
    try:
        document = container.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError("Document not found")
        delivery = container.integration_service.get_delivery(document_id, context)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return {
        "document_id": str(document_id),
        "delivery": erp_delivery_projection(delivery, document_status=document.status),
    }


@router.post("/erpnext/documents/{document_id}/draft")
def create_erpnext_draft(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _require_erpnext(container)
    try:
        result = container.integration_service.send_approved_invoice(
            document_id,
            context,
        )
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (IntegrationIdempotencyConflict, IntegrationOutcomeUnknown) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except IntegrationDeliveryError as exc:
        raise _erpnext_delivery_error(exc) from exc
    document = container.documents.get(document_id)
    return {
        "document_id": str(document_id),
        "delivery": {
            **erp_delivery_projection(result.delivery, document_status=document.status),
            "replayed": result.replayed,
        },
    }


@router.post("/erpnext/documents/{document_id}/delivery/reconcile")
def reconcile_erpnext_delivery(
    document_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _require_erpnext(container)
    try:
        delivery = container.integration_service.reconcile_provider_delivery(
            document_id,
            context,
        )
        document = container.documents.get(document_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except (IntegrationIdempotencyConflict, IntegrationOutcomeUnknown) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrationDeliveryError as exc:
        raise _erpnext_delivery_error(exc) from exc
    return {
        "document_id": str(document_id),
        "delivery": erp_delivery_projection(delivery, document_status=document.status),
    }


@router.post("/accounting/deliveries/reconcile")
def reconcile_accounting_delivery(
    payload: ReconcileDeliveryRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        delivery = container.integration_service.reconcile_delivery(
            idempotency_key=idempotency_key,
            context=context,
            succeeded=payload.succeeded,
            external_id=payload.external_id,
            reason=payload.reason,
        )
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except IntegrationIdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidStatusTransition, IntegrationOutcomeUnknown) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {
        "delivery": {
            "document_id": str(delivery.document_id),
            "adapter_name": delivery.adapter_name,
            "status": delivery.status.value,
            "external_id": delivery.external_id,
            "retryable": delivery.retryable,
            "attempt_count": delivery.attempt_count,
            "updated_at": delivery.updated_at.isoformat(),
        }
    }


def _require_erpnext(container: AppContainer) -> None:
    if container.integration_service.adapter.name != "erpnext-purchase-invoice-draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ERPNext draft delivery is not configured",
        )


def _erpnext_delivery_error(exc: IntegrationDeliveryError) -> HTTPException:
    return HTTPException(
        status_code=(
            status.HTTP_409_CONFLICT
            if not exc.retryable and not exc.outcome_unknown
            else status.HTTP_502_BAD_GATEWAY
        ),
        detail={
            "message": str(exc),
            "code": exc.code,
            "retryable": exc.retryable,
            "outcome_unknown": exc.outcome_unknown,
        },
    )
