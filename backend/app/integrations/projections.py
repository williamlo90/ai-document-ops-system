from __future__ import annotations

from app.documents.status import DocumentStatus
from app.integrations.models import IntegrationDeliveryRecord, IntegrationDeliveryStatus


def erp_delivery_projection(
    record: IntegrationDeliveryRecord | None,
    *,
    document_status: DocumentStatus,
) -> dict[str, object]:
    if record is None:
        ready = document_status == DocumentStatus.APPROVED
        return {
            "status": "ready" if ready else "not_ready",
            "label": "Ready to create ERP draft" if ready else "Not ready for ERP",
            "can_create": ready,
            "can_reconcile": False,
            "can_retry": False,
            "attempt_count": 0,
            "external_id": None,
            "external_url": None,
            "provider_docstatus": None,
            "error_code": None,
            "error_message": None,
            "updated_at": None,
        }
    if record.status == IntegrationDeliveryStatus.SUCCEEDED:
        status = "succeeded"
        label = "ERP draft created"
    elif record.status == IntegrationDeliveryStatus.PENDING:
        status = "pending"
        label = "Creating ERP draft"
    elif record.status == IntegrationDeliveryStatus.UNKNOWN:
        status = "unknown"
        label = "Checking whether ERP saved the draft"
    elif record.retryable:
        status = "failed_retryable"
        label = "ERP draft was not created"
    else:
        status = "failed_permanent"
        label = "ERP draft needs attention"
    return {
        "status": status,
        "label": label,
        "can_create": False,
        "can_reconcile": record.status
        in {IntegrationDeliveryStatus.PENDING, IntegrationDeliveryStatus.UNKNOWN},
        "can_retry": record.status == IntegrationDeliveryStatus.FAILED
        and record.retryable
        and record.attempt_count < 3
        and document_status == DocumentStatus.APPROVED,
        "attempt_count": record.attempt_count,
        "external_id": record.external_id,
        "external_url": record.external_url,
        "provider_docstatus": record.provider_docstatus,
        "error_code": record.error_code,
        "error_message": record.error_detail,
        "updated_at": record.updated_at.isoformat(),
    }
