from __future__ import annotations

from decimal import Decimal

from app.documents.jobs import ProcessingJob
from app.documents.models import AuditEvent, DocumentRecord, ReviewTask
from app.documents.repositories import StoredExtraction
from app.extraction.schemas import SCHEMA_VERSION


SUPPORTED_DOCUMENT_TYPE = "invoice"


def document_response(document: DocumentRecord) -> dict[str, object]:
    return {
        "id": str(document.id),
        "workspace_id": document.workspace_id,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "submitted_by": document.submitted_by,
        "size_bytes": document.size_bytes,
        "document_type": SUPPORTED_DOCUMENT_TYPE,
        "supported_extraction_schema": SCHEMA_VERSION,
        "status": document.status.value,
        "error_message": document.error_message,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


def job_response(job: ProcessingJob) -> dict[str, object]:
    return {
        "id": str(job.id),
        "document_id": str(job.document_id),
        "status": job.status.value,
        "attempt_count": job.attempt_count,
        "error_message": job.error_message,
        "provider_name": job.provider_name,
    }


def audit_response(event: AuditEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "document_id": str(event.document_id),
        "event_type": event.event_type,
        "actor": event.actor,
        "old_status": event.old_status.value if event.old_status else None,
        "new_status": event.new_status.value if event.new_status else None,
        "payload_summary": event.payload_summary,
        "created_at": event.created_at.isoformat(),
    }


def review_task_response(task: ReviewTask) -> dict[str, object]:
    return {
        "id": str(task.id),
        "document_id": str(task.document_id),
        "status": task.status,
        "reviewer_notes": task.reviewer_notes,
        "assigned_to": task.assigned_to,
        "reviewed_by": task.reviewed_by,
        "reviewed_at": task.reviewed_at.isoformat() if task.reviewed_at else None,
    }


def extraction_response(stored: StoredExtraction | None) -> dict[str, object] | None:
    if stored is None:
        return None
    data = stored.extraction_result.extraction.data
    return {
        "provider_name": stored.extraction_result.provider_name,
        "document_type": SUPPORTED_DOCUMENT_TYPE,
        "schema_version": stored.extraction_result.extraction.schema_version,
        "data": {
            "vendor_name": data.vendor_name,
            "invoice_number": data.invoice_number,
            "invoice_date": data.invoice_date.isoformat() if data.invoice_date else None,
            "due_date": data.due_date.isoformat() if data.due_date else None,
            "subtotal": _decimal(data.subtotal),
            "tax": _decimal(data.tax),
            "total": _decimal(data.total),
            "currency": data.currency,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": _decimal(item.quantity),
                    "unit_price": _decimal(item.unit_price),
                    "amount": _decimal(item.amount),
                }
                for item in data.line_items
            ],
        },
        "validation": [
            {
                "field_name": issue.field_name,
                "severity": issue.severity.value,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in stored.validation_report.issues
        ],
        "confidence": [
            {
                "field_name": field.field_name,
                "score": field.score,
                "source_page": field.source_page,
                "source_text": field.source_text,
            }
            for field in stored.extraction_result.extraction.confidence
        ],
    }


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
