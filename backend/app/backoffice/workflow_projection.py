from __future__ import annotations

from dataclasses import dataclass

from app.backoffice.models import WorkItem, WorkItemStatus
from app.backoffice.repositories import ApprovalRepository
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus


@dataclass(frozen=True)
class WorkflowProjection:
    current_stage: str
    current_owner: str
    waiting_for: str | None
    next_action: str
    attention_reason: str | None


def project_workflow(
    document: DocumentRecord,
    work_item: WorkItem | None,
    approvals: ApprovalRepository,
) -> WorkflowProjection:
    pending_for_item = False
    if work_item is not None:
        pending_for_item = any(
            item.work_item_id == work_item.id
            for item in approvals.list_pending(work_item.workspace_id)
        )
    return project_workflow_state(document, work_item, pending_for_item=pending_for_item)


def project_workflow_state(
    document: DocumentRecord,
    work_item: WorkItem | None,
    *,
    pending_for_item: bool,
) -> WorkflowProjection:
    document_projection = _document_status_projection(document)
    if document_projection is not None:
        return document_projection
    if work_item is None:
        return _without_work_item(document)
    return _with_work_item(work_item, pending_for_item=pending_for_item)


def _document_status_projection(document: DocumentRecord) -> WorkflowProjection | None:
    if document.status == DocumentStatus.FAILED:
        return WorkflowProjection(
            "failed",
            "Administrator",
            "Manual retry",
            "Retry document processing",
            document.error_message or "Document processing failed.",
        )
    if document.status in {
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,
        DocumentStatus.PROCESSING,
    }:
        return WorkflowProjection(
            "extracting",
            "AI Workflow",
            "Processing worker" if document.status == DocumentStatus.QUEUED else None,
            "Wait for extraction to finish",
            None,
        )
    if document.status == DocumentStatus.REJECTED:
        return WorkflowProjection(
            "rejected",
            "Intake Operator",
            "Corrected invoice",
            "Upload or correct the invoice",
            "The reviewer rejected this document.",
        )
    if document.status == DocumentStatus.CANCELLED:
        return WorkflowProjection(
            "cancelled",
            "Intake Operator",
            None,
            "Reprocess or upload another invoice",
            None,
        )
    return None


def _without_work_item(document: DocumentRecord) -> WorkflowProjection:
    if document.status == DocumentStatus.NEEDS_REVIEW:
        return WorkflowProjection(
            "needs_verification",
            "Reviewer",
            "Human verification",
            "Review extracted invoice data",
            "Validation requires human review.",
        )
    if document.status == DocumentStatus.EXPORTED:
        return WorkflowProjection("completed", "System", None, "No action required", None)
    return WorkflowProjection(
        "ready_to_submit",
        "Intake Operator",
        "Business outcome",
        "Submit invoice for processing",
        None,
    )


def _with_work_item(
    work_item: WorkItem,
    *,
    pending_for_item: bool,
) -> WorkflowProjection:
    correction_state = work_item.business_context.get("correction_state")
    if correction_state == "requested":
        return WorkflowProjection(
            "correction_requested",
            "Uploader",
            "Corrected invoice data",
            "Correct the invoice and send it back",
            work_item.business_context.get("correction_reason")
            or "The reviewer requested a correction.",
        )
    if correction_state == "submitted":
        return WorkflowProjection(
            "waiting_approval",
            "Reviewer",
            "Reviewer decision",
            "Check the corrected invoice",
            None,
        )
    if pending_for_item:
        return WorkflowProjection(
            "waiting_approval",
            "Reviewer",
            "Approval decision",
            "Approve or reject the proposed action",
            "A controlled action requires explicit human approval.",
        )
    if work_item.status == WorkItemStatus.AWAITING_HUMAN:
        return WorkflowProjection(
            "needs_attention",
            "Reviewer",
            "Human decision",
            "Review the latest activity and decide",
            "The workflow was escalated to a human.",
        )
    if work_item.status in {WorkItemStatus.BLOCKED, WorkItemStatus.FAILED}:
        return WorkflowProjection(
            "failed",
            "Administrator",
            "Failure resolution",
            "Inspect failure and retry or escalate",
            f"Work item is {work_item.status.value}.",
        )
    if work_item.status == WorkItemStatus.RESOLVED:
        return WorkflowProjection("completed", "System", None, "No action required", None)
    return WorkflowProjection(
        "planning",
        "AI Workflow",
        None,
        "Review or execute the generated plan",
        None,
    )
