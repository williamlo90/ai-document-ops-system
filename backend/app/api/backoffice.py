from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.api.serializers import SUPPORTED_DOCUMENT_TYPE
from app.backoffice.models import (
    ActionDraft,
    ActionStep,
    Approval,
    PolicyDecision,
    TaskPlan,
    WorkItem,
    WorkItemPriority,
    WorkType,
)
from app.backoffice.evidence import planning_input_from_evidence
from app.backoffice.services import BackofficeWorkflowError
from app.core.security import SecurityContext
from app.documents.models import DocumentRecord
from app.documents.repositories import NotFoundError
from app.extraction.schemas import SCHEMA_VERSION


router = APIRouter(prefix="/backoffice", tags=["backoffice"])


class WorkItemCreatePayload(BaseModel):
    title: str
    work_type: WorkType | None = None
    linked_document_ids: list[UUID] = Field(default_factory=list)
    requested_outcome: str | None = None


class PlanWorkItemPayload(BaseModel):
    requested_outcome: str | None = None


class ApprovalReviewPayload(BaseModel):
    notes: str | None = None


class WorkItemUpdatePayload(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    priority: WorkItemPriority | None = None
    assignee: str | None = Field(default=None, max_length=120)
    requested_outcome: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None


class DraftEditPayload(BaseModel):
    preview_content: str = Field(min_length=1, max_length=10000)


@router.get("/workspace")
def backoffice_workspace(
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    work_items = sorted(
        container.backoffice_work_items.list_by_workspace(context.workspace_id),
        key=lambda item: item.updated_at,
        reverse=True,
    )
    pending = container.backoffice_approvals.list_pending(context.workspace_id)
    documents = container.documents.list_by_workspace(context.workspace_id)
    return {
        "workspace_id": context.workspace_id,
        "work_items": [_work_item_summary(item) for item in work_items],
        "pending_approvals": [_approval_response(item) for item in pending],
        "documents": [_workspace_document_summary(container, document) for document in documents],
        "metrics": {
            "work_items": len(work_items),
            "pending_approvals": len(pending),
            "drafts": sum(
                len(container.backoffice_drafts.list_for_work_item(context.workspace_id, item.id))
                for item in work_items
            ),
            "policy_decisions": sum(
                len(
                    container.backoffice_policy_decisions.list_for_work_item(
                        context.workspace_id, item.id
                    )
                )
                for item in work_items
            ),
        },
    }


def _workspace_document_summary(
    container: AppContainer, document: DocumentRecord
) -> dict[str, object]:
    try:
        stored = container.extractions.get_for_document(document.id)
    except NotFoundError:
        issues = ()
    else:
        issues = stored.validation_report.issues
    error_issues = tuple(issue for issue in issues if issue.severity.value == "error")
    return {
        "id": str(document.id),
        "filename": document.original_filename,
        "status": document.status.value,
        "document_type": SUPPORTED_DOCUMENT_TYPE,
        "supported_extraction_schema": SCHEMA_VERSION,
        "created_at": document.created_at.isoformat(),
        "validation_issue_count": len(issues),
        "validation_error_count": len(error_issues),
        "has_validation_errors": bool(error_issues),
        "validation_codes": sorted({issue.code for issue in error_issues}),
    }


@router.post("/work-items", status_code=status.HTTP_201_CREATED)
def create_work_item(
    payload: WorkItemCreatePayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    work_item = container.backoffice_service.create_work_item(
        title=payload.title.strip() or "Untitled work item",
        context=context,
        work_type=payload.work_type,
        linked_document_ids=_linked_document_ids_for_context(container, context, payload),
        business_context={
            "requested_outcome": payload.requested_outcome or "",
        },
        idempotency_key=idempotency_key,
    )
    return {"work_item": _work_item_summary(work_item)}


@router.get("/work-items/{work_item_id}")
def get_work_item(
    work_item_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    work_item = _work_item_for_context(container, context, work_item_id)
    return {"work_item": _work_item_detail(container, context, work_item)}


@router.patch("/work-items/{work_item_id}")
def update_work_item(
    work_item_id: UUID,
    payload: WorkItemUpdatePayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        work_item = container.backoffice_service.update_work_item(
            work_item_id=work_item_id,
            context=context,
            title=payload.title,
            priority=payload.priority,
            assignee=payload.assignee,
            requested_outcome=payload.requested_outcome,
            tags=tuple(payload.tags) if payload.tags is not None else None,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return {"work_item": _work_item_detail(container, context, work_item)}


@router.patch("/work-items/{work_item_id}/drafts/{draft_id}")
def edit_draft(
    work_item_id: UUID,
    draft_id: UUID,
    payload: DraftEditPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        draft = container.backoffice_service.edit_draft(
            work_item_id=work_item_id,
            draft_id=draft_id,
            context=context,
            preview_content=payload.preview_content,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except BackofficeWorkflowError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"draft": _draft_response(draft)}


@router.post("/work-items/{work_item_id}/drafts/{draft_id}/regenerate")
def regenerate_draft(
    work_item_id: UUID,
    draft_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        draft = container.backoffice_service.regenerate_draft(
            work_item_id=work_item_id,
            draft_id=draft_id,
            context=context,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    return {"draft": _draft_response(draft)}


@router.post("/work-items/{work_item_id}/plan")
def plan_work_item(
    work_item_id: UUID,
    payload: PlanWorkItemPayload,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        work_item = _work_item_for_context(container, context, work_item_id)
        result = container.backoffice_service.plan_work_item(
            work_item_id=work_item_id,
            context=context,
            planning_input=planning_input_from_evidence(
                work_item=work_item,
                requested_outcome=payload.requested_outcome,
                documents=container.documents,
                extractions=container.extractions,
            ),
            idempotency_key=idempotency_key,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except BackofficeWorkflowError as exc:
        raise _backoffice_workflow_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"work_item": _work_item_detail(container, context, result.work_item)}


@router.post("/approvals/{approval_id}/approve")
def approve_request(
    approval_id: UUID,
    payload: ApprovalReviewPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        approval = container.backoffice_service.approve_request(
            approval_id=approval_id,
            context=context,
            notes=payload.notes,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"approval": _approval_response(approval)}


@router.post("/approvals/{approval_id}/reject")
def reject_request(
    approval_id: UUID,
    payload: ApprovalReviewPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        approval = container.backoffice_service.reject_request(
            approval_id=approval_id,
            context=context,
            notes=payload.notes,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"approval": _approval_response(approval)}


@router.post("/work-items/{work_item_id}/steps/{action_step_id}/execute")
def execute_step(
    work_item_id: UUID,
    action_step_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        response = container.backoffice_service.execute_approved_step(
            work_item_id=work_item_id,
            action_step_id=action_step_id,
            context=context,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    except BackofficeWorkflowError as exc:
        raise _backoffice_workflow_http_error(exc) from exc
    work_item = _work_item_for_context(container, context, work_item_id)
    return {
        "tool_response": {
            "tool_name": response.tool_name.value,
            "status": response.status,
            "risk": response.risk.value,
            "summary": response.summary,
            "failure_type": response.failure_type.value if response.failure_type else None,
            "human_escalation_reason": response.human_escalation_reason,
        },
        "work_item": _work_item_detail(container, context, work_item),
    }


def _work_item_for_context(
    container: AppContainer, context: SecurityContext, work_item_id: UUID
) -> WorkItem:
    try:
        work_item = container.backoffice_work_items.get(work_item_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if work_item.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return work_item


def _linked_document_ids_for_context(
    container: AppContainer, context: SecurityContext, payload: WorkItemCreatePayload
) -> tuple[UUID, ...]:
    linked_document_ids = tuple(payload.linked_document_ids)
    for document_id in linked_document_ids:
        try:
            document = container.documents.get(document_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
        if document.workspace_id != context.workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return linked_document_ids


def _backoffice_workflow_http_error(exc: BackofficeWorkflowError) -> HTTPException:
    if str(exc) == "Idempotency key is too long.":
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Backoffice action is not ready for that operation.",
    )


def _work_item_summary(work_item: WorkItem) -> dict[str, object]:
    tags = [item for item in work_item.business_context.get("tags", "").split(",") if item]
    return {
        "id": str(work_item.id),
        "workspace_id": work_item.workspace_id,
        "title": work_item.title,
        "work_type": work_item.work_type.value if work_item.work_type else None,
        "priority": work_item.priority.value,
        "status": work_item.status.value,
        "linked_document_ids": [str(item) for item in work_item.linked_document_ids],
        "business_context": dict(work_item.business_context),
        "assignee": work_item.business_context.get("assignee") or "Unassigned",
        "requested_outcome": work_item.business_context.get("requested_outcome") or "",
        "tags": tags,
        "current_plan_id": str(work_item.current_plan_id) if work_item.current_plan_id else None,
        "created_at": work_item.created_at.isoformat(),
        "updated_at": work_item.updated_at.isoformat(),
    }


def _work_item_detail(
    container: AppContainer, context: SecurityContext, work_item: WorkItem
) -> dict[str, object]:
    plans = container.backoffice_plans.list_for_work_item(context.workspace_id, work_item.id)
    current_plan = None
    if work_item.current_plan_id is not None:
        try:
            current_plan = container.backoffice_plans.get(work_item.current_plan_id)
        except NotFoundError:
            current_plan = None
    drafts = container.backoffice_drafts.list_for_work_item(context.workspace_id, work_item.id)
    approvals = container.backoffice_approvals.list_for_work_item(
        context.workspace_id, work_item.id
    )
    decisions = container.backoffice_policy_decisions.list_for_work_item(
        context.workspace_id, work_item.id
    )
    payload = _work_item_summary(work_item)
    payload.update(
        {
            "plans": [_plan_response(plan) for plan in plans],
            "current_plan": _plan_response(current_plan) if current_plan else None,
            "drafts": [_draft_response(draft) for draft in drafts],
            "approvals": [_approval_response(approval) for approval in approvals],
            "policy_decisions": [_policy_decision_response(decision) for decision in decisions],
            "activity": [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "actor": event.actor,
                    "summary": event.summary,
                    "agent_run_id": str(event.agent_run_id) if event.agent_run_id else None,
                    "created_at": event.created_at.isoformat(),
                }
                for event in container.workflow_events.list_for_work_item(
                    context.workspace_id, work_item.id
                )
            ],
        }
    )
    return payload


def _plan_response(plan: TaskPlan) -> dict[str, object]:
    return {
        "id": str(plan.id),
        "workspace_id": plan.workspace_id,
        "work_item_id": str(plan.work_item_id),
        "planner_version": plan.planner_version,
        "overall_confidence": plan.overall_confidence,
        "escalation_reason": plan.escalation_reason,
        "requires_human": plan.requires_human,
        "agent_run_id": str(plan.agent_run_id) if plan.agent_run_id else None,
        "created_at": plan.created_at.isoformat(),
        "steps": [_step_response(step) for step in plan.steps],
    }


def _step_response(step: ActionStep) -> dict[str, object]:
    return {
        "id": str(step.id),
        "action_type": step.action_type.value,
        "risk_level": step.risk_level.value,
        "tool_name": step.tool_name,
        "requires_approval": step.requires_approval,
        "status": step.status.value,
        "why_this": step.why_this,
        "why_not": step.why_not,
    }


def _draft_response(draft: ActionDraft) -> dict[str, object]:
    return {
        "id": str(draft.id),
        "work_item_id": str(draft.work_item_id),
        "action_step_id": str(draft.action_step_id) if draft.action_step_id else None,
        "draft_type": draft.draft_type.value,
        "status": draft.status.value,
        "preview_content": draft.preview_content,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def _approval_response(approval: Approval) -> dict[str, object]:
    return {
        "id": str(approval.id),
        "work_item_id": str(approval.work_item_id),
        "action_step_id": str(approval.action_step_id) if approval.action_step_id else None,
        "draft_id": str(approval.draft_id) if approval.draft_id else None,
        "status": approval.status.value,
        "requested_by": approval.requested_by,
        "reviewed_by": approval.reviewed_by,
        "reviewer_notes": approval.reviewer_notes,
        "created_at": approval.created_at.isoformat(),
        "reviewed_at": approval.reviewed_at.isoformat() if approval.reviewed_at else None,
    }


def _policy_decision_response(decision: PolicyDecision) -> dict[str, object]:
    return {
        "id": str(decision.id),
        "work_item_id": str(decision.work_item_id),
        "action_step_id": str(decision.action_step_id) if decision.action_step_id else None,
        "action_type": decision.action_type.value,
        "autonomy_level": decision.autonomy_level.value,
        "risk_level": decision.risk_level.value,
        "allowed": decision.allowed,
        "requires_confirmation": decision.requires_confirmation,
        "reason": decision.reason,
        "created_at": decision.created_at.isoformat(),
    }
