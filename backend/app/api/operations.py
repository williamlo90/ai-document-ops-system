from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.serializers import job_response
from app.core.security import SecurityContext, UnauthorizedError
from app.documents.jobs import ProcessingJobStatus
from app.documents.repositories import NotFoundError
from app.documents.status import InvalidStatusTransition
from app.operations.notifications import Notification, notification_response


router = APIRouter(prefix="/operations", tags=["operations"])


class RetentionPurgeRequest(BaseModel):
    dry_run: bool = True
    reason: str = Field(
        default="retention_policy",
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9_-]+$",
    )


@router.get("/retention")
def retention_policy(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.retention_service.policy(context)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc


@router.post("/retention/purge")
def purge_expired_documents(
    payload: RetentionPurgeRequest,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        return container.retention_service.purge_expired(
            context,
            dry_run=payload.dry_run,
            reason=payload.reason,
        )
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc


@router.get("/notifications")
def list_notifications(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    _project_notifications(context, container)
    records = container.notifications.list_recent(context.workspace_id)
    return {
        "unread_count": sum(record.read_at is None for record in records),
        "notifications": [notification_response(record) for record in records],
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        item = container.notifications.get(notification_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if item.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    item.mark_read()
    return {"notification": notification_response(container.notifications.save(item))}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, int]:
    count = 0
    for item in container.notifications.list_recent(context.workspace_id, limit=1000):
        if item.read_at is None:
            item.mark_read()
            container.notifications.save(item)
            count += 1
    return {"marked_read": count}


@router.get("/jobs")
def operational_jobs(
    failure_page: int = Query(default=1, ge=1),
    failure_page_size: int = Query(default=100, ge=1, le=200),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    stalled_before = datetime.now(UTC) - timedelta(minutes=5)
    failure_offset = (failure_page - 1) * failure_page_size
    if container.operations_queries is not None:
        snapshot = container.operations_queries.job_health(
            context.workspace_id,
            stalled_before=stalled_before,
            failure_offset=failure_offset,
            failure_limit=failure_page_size,
        )
        failures = list(snapshot.failures)
        queued_count = snapshot.queued_jobs
        failed_count = snapshot.failed_jobs
        stalled_count = snapshot.stalled_jobs
    else:
        document_ids = {
            document.id for document in container.documents.list_by_workspace(context.workspace_id)
        }
        jobs = [job for job in container.jobs.list_all() if job.document_id in document_ids]
        failures = [
            job
            for job in jobs
            if job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTER}
        ]
        failures.sort(key=lambda job: (job.updated_at, str(job.id)), reverse=True)
        queued_count = sum(
            job.status in {ProcessingJobStatus.QUEUED, ProcessingJobStatus.RETRYING} for job in jobs
        )
        failed_count = len(failures)
        failures = failures[failure_offset : failure_offset + failure_page_size]
        stalled_count = sum(
            job.status == ProcessingJobStatus.RUNNING and job.updated_at < stalled_before
            for job in jobs
        )
    return {
        "worker": {
            "status": "degraded" if stalled_count else "healthy",
            "queued_jobs": queued_count,
            "failed_jobs": failed_count,
            "stalled_jobs": stalled_count,
            "evidence": (
                "No processing job has been running for more than five minutes."
                if not stalled_count
                else "One or more processing jobs appear stalled."
            ),
        },
        "failed_jobs": [job_response(job) for job in failures],
        "failed_jobs_pagination": {
            "page": failure_page,
            "page_size": failure_page_size,
            "returned": len(failures),
            "total": failed_count,
            "total_pages": max(1, (failed_count + failure_page_size - 1) // failure_page_size),
        },
    }


@router.post("/jobs/{job_id}/retry")
def retry_operational_job(
    job_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        job = container.jobs.get(job_id)
        document = container.documents.get(job.document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError("Not found")
        container.processing_service.retry_failed_document(document.id, context)
        new_job = container.jobs.get_latest_for_document(document.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"job": job_response(new_job)}


@router.get("/audit.csv")
def export_audit_log(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "event_id",
            "document_id",
            "event_type",
            "actor",
            "old_status",
            "new_status",
            "details",
            "created_at",
        ]
    )
    for document in container.documents.list_by_workspace(context.workspace_id):
        for event in container.audits.list_for_document(document.id):
            writer.writerow(
                [
                    str(event.id),
                    str(event.document_id),
                    event.event_type,
                    event.actor,
                    event.old_status.value if event.old_status else "",
                    event.new_status.value if event.new_status else "",
                    event.payload_summary or "",
                    event.created_at.isoformat(),
                ]
            )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


def _project_notifications(context: SecurityContext, container: AppContainer) -> None:
    event_mapping = {
        "approval_requested": ("approval_requested", "Approval required", "warning"),
        "work_item_updated": ("assignment_updated", "Work item assignment updated", "info"),
        "action_failed": ("execution_failed", "Controlled execution failed", "error"),
        "workflow_escalated": ("workflow_escalated", "Workflow needs attention", "warning"),
        "action_executed": ("execution_completed", "Controlled execution completed", "success"),
    }
    for work_item in container.backoffice_work_items.list_by_workspace(context.workspace_id):
        for event in container.workflow_events.list_for_work_item(
            context.workspace_id, work_item.id
        ):
            mapped = event_mapping.get(event.event_type)
            if mapped:
                notification_type, title, severity = mapped
                container.notifications.add(
                    Notification(
                        workspace_id=context.workspace_id,
                        source_key=f"workflow:{event.id}",
                        notification_type=notification_type,
                        title=title,
                        message=event.summary,
                        severity=severity,
                        work_item_id=work_item.id,
                        document_id=event.document_id,
                        created_at=event.created_at,
                    )
                )
    documents = {
        document.id: document
        for document in container.documents.list_by_workspace(context.workspace_id)
    }
    for job in container.jobs.list_all():
        if job.document_id in documents and job.status in {
            ProcessingJobStatus.FAILED,
            ProcessingJobStatus.DEAD_LETTER,
        }:
            container.notifications.add(
                Notification(
                    workspace_id=context.workspace_id,
                    source_key=f"job:{job.id}:{job.status.value}",
                    notification_type="job_failed",
                    title="Document processing failed",
                    message=job.error_message or "The processing job failed.",
                    severity="error",
                    document_id=job.document_id,
                    created_at=job.updated_at,
                )
            )
