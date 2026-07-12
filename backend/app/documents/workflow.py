from __future__ import annotations

from datetime import UTC, datetime

from app.documents.models import AuditEvent, DocumentRecord
from app.documents.status import DocumentStatus, require_transition


STATUS_EVENT_NAMES: dict[DocumentStatus, str] = {
    DocumentStatus.QUEUED: "processing_queued",
    DocumentStatus.PROCESSING: "processing_started",
    DocumentStatus.EXTRACTED: "processing_finished",
    DocumentStatus.NEEDS_REVIEW: "review_required",
    DocumentStatus.APPROVED: "document_approved",
    DocumentStatus.REJECTED: "document_rejected",
    DocumentStatus.FAILED: "processing_failed",
    DocumentStatus.EXPORTED: "document_exported",
    DocumentStatus.CANCELLED: "intake_cancelled",
}


class DocumentWorkflowService:
    def transition(
        self,
        document: DocumentRecord,
        target_status: DocumentStatus,
        actor: str,
        payload_summary: str | None = None,
    ) -> AuditEvent:
        old_status = document.status
        require_transition(old_status, target_status)
        document.status = target_status
        document.updated_at = datetime.now(UTC)
        event = AuditEvent(
            document_id=document.id,
            event_type=STATUS_EVENT_NAMES[target_status],
            actor=actor,
            old_status=old_status,
            new_status=target_status,
            payload_summary=payload_summary,
        )
        return event

    def record_upload(self, document: DocumentRecord, actor: str) -> AuditEvent:
        return AuditEvent(
            document_id=document.id,
            event_type="document_uploaded",
            actor=actor,
            new_status=document.status,
        )
