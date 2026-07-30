from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from app.backoffice.models import (
    ActionDraft,
    ActionRiskLevel,
    ActionStep,
    ActionStepStatus,
    ActionType,
    Approval,
    ApprovalStatus,
    AutonomyLevel,
    DraftStatus,
    DraftType,
    PolicyDecision,
    TaskPlan,
    WorkflowEvent,
    WorkItem,
    WorkItemPriority,
    WorkItemSourceType,
    WorkItemStatus,
    WorkType,
)
from app.documents.repositories import NotFoundError
from app.documents.sqlite_repositories import SqliteStore


class SqliteWorkItemRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, work_item: WorkItem) -> WorkItem:
        with self.store.transaction():
            self.store.execute(
                """
                INSERT INTO backoffice_work_items
                (id, workspace_id, idempotency_key, updated_at, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    idempotency_key = excluded.idempotency_key,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    str(work_item.id),
                    work_item.workspace_id,
                    work_item.idempotency_key,
                    work_item.updated_at.isoformat(),
                    json.dumps(_work_item_to_dict(work_item)),
                ),
            )
            self.store.execute(
                "DELETE FROM backoffice_work_item_documents WHERE work_item_id = ?",
                (str(work_item.id),),
            )
            for document_id in work_item.linked_document_ids:
                self.store.execute(
                    """
                    INSERT INTO backoffice_work_item_documents
                    (work_item_id, workspace_id, document_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(work_item.id),
                        work_item.workspace_id,
                        str(document_id),
                        work_item.updated_at.isoformat(),
                    ),
                )
        return work_item

    def get(self, work_item_id: UUID) -> WorkItem:
        row = self.store.query_one(
            "SELECT payload FROM backoffice_work_items WHERE id = ?",
            (str(work_item_id),),
        )
        if row is None:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        return _work_item_from_dict(json.loads(row["payload"]))

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> WorkItem | None:
        row = self.store.query_one(
            """
            SELECT payload FROM backoffice_work_items
            WHERE workspace_id = ? AND idempotency_key = ?
            """,
            (workspace_id, idempotency_key),
        )
        return _work_item_from_dict(json.loads(row["payload"])) if row else None

    def list_by_workspace(self, workspace_id: str) -> list[WorkItem]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_work_items
            WHERE workspace_id = ? ORDER BY updated_at DESC
            """,
            (workspace_id,),
        )
        return [_work_item_from_dict(json.loads(row["payload"])) for row in rows]

    def get_latest_for_documents(
        self,
        workspace_id: str,
        document_ids: list[UUID],
    ) -> dict[UUID, WorkItem]:
        if not document_ids:
            return {}
        placeholders = ", ".join("?" for _ in document_ids)
        rows = self.store.query(
            f"""
            WITH ranked AS (
                SELECT document_id, work_item_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY document_id
                           ORDER BY updated_at DESC, work_item_id DESC
                       ) AS position
                FROM backoffice_work_item_documents
                WHERE workspace_id = ?
                  AND document_id IN ({placeholders})
            )
            SELECT ranked.document_id, items.payload
            FROM ranked
            JOIN backoffice_work_items items ON items.id = ranked.work_item_id
            WHERE ranked.position = 1
            """,
            (workspace_id, *(str(document_id) for document_id in document_ids)),
        )
        return {
            UUID(row["document_id"]): _work_item_from_dict(json.loads(row["payload"]))
            for row in rows
        }


class SqliteTaskPlanRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, plan: TaskPlan) -> TaskPlan:
        self.store.execute(
            """
            INSERT INTO backoffice_task_plans
            (id, workspace_id, work_item_id, idempotency_key, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                work_item_id = excluded.work_item_id,
                idempotency_key = excluded.idempotency_key,
                created_at = excluded.created_at,
                payload = excluded.payload
            """,
            (
                str(plan.id),
                plan.workspace_id,
                str(plan.work_item_id),
                plan.idempotency_key,
                plan.created_at.isoformat(),
                json.dumps(_task_plan_to_dict(plan)),
            ),
        )
        return plan

    def get(self, plan_id: UUID) -> TaskPlan:
        row = self.store.query_one(
            "SELECT payload FROM backoffice_task_plans WHERE id = ?",
            (str(plan_id),),
        )
        if row is None:
            raise NotFoundError(f"Task plan not found: {plan_id}")
        return _task_plan_from_dict(json.loads(row["payload"]))

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        work_item_id: UUID,
        idempotency_key: str,
    ) -> TaskPlan | None:
        row = self.store.query_one(
            """
            SELECT payload FROM backoffice_task_plans
            WHERE workspace_id = ? AND work_item_id = ? AND idempotency_key = ?
            """,
            (workspace_id, str(work_item_id), idempotency_key),
        )
        return _task_plan_from_dict(json.loads(row["payload"])) if row else None

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[TaskPlan]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_task_plans
            WHERE workspace_id = ? AND work_item_id = ? ORDER BY created_at
            """,
            (workspace_id, str(work_item_id)),
        )
        return [_task_plan_from_dict(json.loads(row["payload"])) for row in rows]


class SqliteActionDraftRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, draft: ActionDraft) -> ActionDraft:
        self.store.execute(
            """
            INSERT OR REPLACE INTO backoffice_action_drafts
            (id, workspace_id, work_item_id, created_at, payload) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(draft.id),
                draft.workspace_id,
                str(draft.work_item_id),
                draft.created_at.isoformat(),
                json.dumps(_action_draft_to_dict(draft)),
            ),
        )
        return draft

    def get(self, draft_id: UUID) -> ActionDraft:
        row = self.store.query_one(
            "SELECT payload FROM backoffice_action_drafts WHERE id = ?",
            (str(draft_id),),
        )
        if row is None:
            raise NotFoundError(f"Action draft not found: {draft_id}")
        return _action_draft_from_dict(json.loads(row["payload"]))

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[ActionDraft]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_action_drafts
            WHERE workspace_id = ? AND work_item_id = ? ORDER BY created_at
            """,
            (workspace_id, str(work_item_id)),
        )
        return [_action_draft_from_dict(json.loads(row["payload"])) for row in rows]


class SqliteApprovalRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, approval: Approval) -> Approval:
        self.store.execute(
            """
            INSERT OR REPLACE INTO backoffice_approvals
            (id, workspace_id, work_item_id, status, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(approval.id),
                approval.workspace_id,
                str(approval.work_item_id),
                approval.status.value,
                approval.created_at.isoformat(),
                json.dumps(_approval_to_dict(approval)),
            ),
        )
        return approval

    def get(self, approval_id: UUID) -> Approval:
        row = self.store.query_one(
            "SELECT payload FROM backoffice_approvals WHERE id = ?",
            (str(approval_id),),
        )
        if row is None:
            raise NotFoundError(f"Approval not found: {approval_id}")
        return _approval_from_dict(json.loads(row["payload"]))

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[Approval]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_approvals
            WHERE workspace_id = ? AND work_item_id = ? ORDER BY created_at
            """,
            (workspace_id, str(work_item_id)),
        )
        return [_approval_from_dict(json.loads(row["payload"])) for row in rows]

    def list_pending(self, workspace_id: str) -> list[Approval]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_approvals
            WHERE workspace_id = ? AND status = ? ORDER BY created_at
            """,
            (workspace_id, ApprovalStatus.PENDING.value),
        )
        return [_approval_from_dict(json.loads(row["payload"])) for row in rows]


class SqlitePolicyDecisionRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, decision: PolicyDecision) -> PolicyDecision:
        self.store.execute(
            """
            INSERT OR REPLACE INTO backoffice_policy_decisions
            (id, workspace_id, work_item_id, created_at, payload) VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(decision.id),
                decision.workspace_id,
                str(decision.work_item_id),
                decision.created_at.isoformat(),
                json.dumps(_policy_decision_to_dict(decision)),
            ),
        )
        return decision

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[PolicyDecision]:
        rows = self.store.query(
            """
            SELECT payload FROM backoffice_policy_decisions
            WHERE workspace_id = ? AND work_item_id = ? ORDER BY created_at
            """,
            (workspace_id, str(work_item_id)),
        )
        return [_policy_decision_from_dict(json.loads(row["payload"])) for row in rows]


class SqliteWorkflowEventRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, event: WorkflowEvent) -> WorkflowEvent:
        self.store.execute(
            """
            INSERT OR REPLACE INTO workflow_events
            (id, workspace_id, document_id, work_item_id, event_type, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                event.workspace_id,
                str(event.document_id) if event.document_id else None,
                str(event.work_item_id) if event.work_item_id else None,
                event.event_type,
                event.created_at.isoformat(),
                json.dumps(_workflow_event_to_dict(event)),
            ),
        )
        return event

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[WorkflowEvent]:
        rows = self.store.query(
            """
            SELECT payload FROM workflow_events
            WHERE workspace_id = ? AND document_id = ? ORDER BY created_at
            """,
            (workspace_id, str(document_id)),
        )
        return [_workflow_event_from_dict(json.loads(row["payload"])) for row in rows]

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[WorkflowEvent]:
        rows = self.store.query(
            """
            SELECT payload FROM workflow_events
            WHERE workspace_id = ? AND work_item_id = ? ORDER BY created_at
            """,
            (workspace_id, str(work_item_id)),
        )
        return [_workflow_event_from_dict(json.loads(row["payload"])) for row in rows]


def _work_item_to_dict(item: WorkItem) -> dict[str, object]:
    return {
        "id": str(item.id),
        "workspace_id": item.workspace_id,
        "title": item.title,
        "source_type": item.source_type.value,
        "work_type": item.work_type.value if item.work_type else None,
        "priority": item.priority.value,
        "status": item.status.value,
        "linked_document_ids": [str(value) for value in item.linked_document_ids],
        "business_context": dict(item.business_context),
        "current_plan_id": str(item.current_plan_id) if item.current_plan_id else None,
        "idempotency_key": item.idempotency_key,
        "idempotency_fingerprint": item.idempotency_fingerprint,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _work_item_from_dict(value: dict[str, object]) -> WorkItem:
    work_type = value.get("work_type")
    current_plan_id = value.get("current_plan_id")
    return WorkItem(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        title=str(value["title"]),
        source_type=WorkItemSourceType(str(value["source_type"])),
        work_type=WorkType(str(work_type)) if work_type else None,
        priority=WorkItemPriority(str(value["priority"])),
        status=WorkItemStatus(str(value["status"])),
        linked_document_ids=tuple(UUID(str(item)) for item in value["linked_document_ids"]),
        business_context={
            str(key): str(item) for key, item in dict(value["business_context"]).items()
        },
        current_plan_id=UUID(str(current_plan_id)) if current_plan_id else None,
        idempotency_key=(str(value["idempotency_key"]) if value.get("idempotency_key") else None),
        idempotency_fingerprint=(
            str(value["idempotency_fingerprint"]) if value.get("idempotency_fingerprint") else None
        ),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _task_plan_to_dict(plan: TaskPlan) -> dict[str, object]:
    return {
        "id": str(plan.id),
        "workspace_id": plan.workspace_id,
        "work_item_id": str(plan.work_item_id),
        "planner_version": plan.planner_version,
        "steps": [_action_step_to_dict(step) for step in plan.steps],
        "overall_confidence": plan.overall_confidence,
        "escalation_reason": plan.escalation_reason,
        "idempotency_key": plan.idempotency_key,
        "idempotency_fingerprint": plan.idempotency_fingerprint,
        "agent_run_id": str(plan.agent_run_id) if plan.agent_run_id else None,
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


def _task_plan_from_dict(value: dict[str, object]) -> TaskPlan:
    return TaskPlan(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        work_item_id=UUID(str(value["work_item_id"])),
        planner_version=str(value["planner_version"]),
        steps=tuple(_action_step_from_dict(item) for item in value["steps"]),
        overall_confidence=str(value["overall_confidence"]),
        escalation_reason=(
            str(value["escalation_reason"]) if value.get("escalation_reason") else None
        ),
        idempotency_key=(str(value["idempotency_key"]) if value.get("idempotency_key") else None),
        idempotency_fingerprint=(
            str(value["idempotency_fingerprint"]) if value.get("idempotency_fingerprint") else None
        ),
        agent_run_id=UUID(str(value["agent_run_id"])) if value.get("agent_run_id") else None,
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _action_step_to_dict(step: ActionStep) -> dict[str, object]:
    return {
        "id": str(step.id),
        "action_type": step.action_type.value,
        "risk_level": step.risk_level.value,
        "tool_name": step.tool_name,
        "requires_approval": step.requires_approval,
        "status": step.status.value,
        "why_this": step.why_this,
        "why_not": step.why_not,
        "created_at": step.created_at.isoformat(),
        "updated_at": step.updated_at.isoformat(),
    }


def _action_step_from_dict(value: dict[str, object]) -> ActionStep:
    return ActionStep(
        id=UUID(str(value["id"])),
        action_type=ActionType(str(value["action_type"])),
        risk_level=ActionRiskLevel(str(value["risk_level"])),
        tool_name=str(value["tool_name"]) if value.get("tool_name") else None,
        requires_approval=bool(value["requires_approval"]),
        status=ActionStepStatus(str(value["status"])),
        why_this=str(value["why_this"]) if value.get("why_this") else None,
        why_not=str(value["why_not"]) if value.get("why_not") else None,
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _action_draft_to_dict(draft: ActionDraft) -> dict[str, object]:
    return {
        "id": str(draft.id),
        "workspace_id": draft.workspace_id,
        "work_item_id": str(draft.work_item_id),
        "action_step_id": str(draft.action_step_id) if draft.action_step_id else None,
        "draft_type": draft.draft_type.value,
        "preview_content": draft.preview_content,
        "status": draft.status.value,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


def _action_draft_from_dict(value: dict[str, object]) -> ActionDraft:
    action_step_id = value.get("action_step_id")
    return ActionDraft(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        work_item_id=UUID(str(value["work_item_id"])),
        action_step_id=UUID(str(action_step_id)) if action_step_id else None,
        draft_type=DraftType(str(value["draft_type"])),
        preview_content=str(value["preview_content"]),
        status=DraftStatus(str(value["status"])),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _approval_to_dict(approval: Approval) -> dict[str, object]:
    return {
        "id": str(approval.id),
        "workspace_id": approval.workspace_id,
        "work_item_id": str(approval.work_item_id),
        "requested_by": approval.requested_by,
        "action_step_id": str(approval.action_step_id) if approval.action_step_id else None,
        "draft_id": str(approval.draft_id) if approval.draft_id else None,
        "status": approval.status.value,
        "reviewed_by": approval.reviewed_by,
        "reviewer_notes": approval.reviewer_notes,
        "reviewed_at": approval.reviewed_at.isoformat() if approval.reviewed_at else None,
        "created_at": approval.created_at.isoformat(),
        "updated_at": approval.updated_at.isoformat(),
    }


def _approval_from_dict(value: dict[str, object]) -> Approval:
    action_step_id = value.get("action_step_id")
    draft_id = value.get("draft_id")
    reviewed_at = value.get("reviewed_at")
    return Approval(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        work_item_id=UUID(str(value["work_item_id"])),
        requested_by=str(value["requested_by"]),
        action_step_id=UUID(str(action_step_id)) if action_step_id else None,
        draft_id=UUID(str(draft_id)) if draft_id else None,
        status=ApprovalStatus(str(value["status"])),
        reviewed_by=str(value["reviewed_by"]) if value.get("reviewed_by") else None,
        reviewer_notes=(str(value["reviewer_notes"]) if value.get("reviewer_notes") else None),
        reviewed_at=datetime.fromisoformat(str(reviewed_at)) if reviewed_at else None,
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _policy_decision_to_dict(decision: PolicyDecision) -> dict[str, object]:
    return {
        "id": str(decision.id),
        "workspace_id": decision.workspace_id,
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


def _policy_decision_from_dict(value: dict[str, object]) -> PolicyDecision:
    action_step_id = value.get("action_step_id")
    return PolicyDecision(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        work_item_id=UUID(str(value["work_item_id"])),
        action_step_id=UUID(str(action_step_id)) if action_step_id else None,
        action_type=ActionType(str(value["action_type"])),
        autonomy_level=AutonomyLevel(str(value["autonomy_level"])),
        risk_level=ActionRiskLevel(str(value["risk_level"])),
        allowed=bool(value["allowed"]),
        requires_confirmation=bool(value["requires_confirmation"]),
        reason=str(value["reason"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )


def _workflow_event_to_dict(event: WorkflowEvent) -> dict[str, object]:
    return {
        "id": str(event.id),
        "workspace_id": event.workspace_id,
        "document_id": str(event.document_id) if event.document_id else None,
        "work_item_id": str(event.work_item_id) if event.work_item_id else None,
        "agent_run_id": str(event.agent_run_id) if event.agent_run_id else None,
        "event_type": event.event_type,
        "actor": event.actor,
        "summary": event.summary,
        "created_at": event.created_at.isoformat(),
    }


def _workflow_event_from_dict(value: dict[str, object]) -> WorkflowEvent:
    document_id = value.get("document_id")
    work_item_id = value.get("work_item_id")
    agent_run_id = value.get("agent_run_id")
    return WorkflowEvent(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        document_id=UUID(str(document_id)) if document_id else None,
        work_item_id=UUID(str(work_item_id)) if work_item_id else None,
        agent_run_id=UUID(str(agent_run_id)) if agent_run_id else None,
        event_type=str(value["event_type"]),
        actor=str(value["actor"]),
        summary=str(value["summary"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )
