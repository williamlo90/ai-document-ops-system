from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.serializers import document_response
from app.core.security import SecurityContext
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition
from app.integrations.models import IntegrationDeliveryError


router = APIRouter(prefix="/integrations", tags=["integrations"])


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
            settings.accounting_provider in {"csv_download", "mock"},
            settings.accounting_sandbox_mode,
            "Approved invoices can be downloaded through the audited CSV export contract.",
        ),
        _status(
            "document_storage",
            settings.document_storage_backend,
            settings.document_storage_backend == "local"
            or all(
                (
                    settings.s3_endpoint_url,
                    settings.s3_bucket,
                    settings.s3_access_key_id,
                    settings.s3_secret_access_key,
                )
            ),
            settings.document_storage_backend == "local",
            (
                "Private local storage."
                if settings.document_storage_backend == "local"
                else "S3-compatible credentials loaded."
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
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        result = container.integration_service.send_approved_invoice(document_id, context)
    except (NotFoundError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Integration delivery failed",
                "code": exc.code,
                "retryable": exc.retryable,
            },
        ) from exc
    return {
        "document": document_response(result.document),
        "integration": {
            "adapter_name": result.integration_result.adapter_name,
            "external_id": result.integration_result.external_id,
            "status": result.integration_result.status,
            "retryable": result.integration_result.retryable,
        },
    }
