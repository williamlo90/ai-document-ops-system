from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.backoffice.models import (
    ActionDraft,
    Approval,
    PolicyDecision,
    TaskPlan,
    WorkflowEvent,
    WorkItem,
)
from app.documents.repositories import NotFoundError


class WorkItemRepository(Protocol):
    def save(self, work_item: WorkItem) -> WorkItem: ...

    def get(self, work_item_id: UUID) -> WorkItem: ...

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> WorkItem | None: ...

    def list_by_workspace(self, workspace_id: str) -> list[WorkItem]: ...

    def get_latest_for_documents(
        self,
        workspace_id: str,
        document_ids: list[UUID],
    ) -> dict[UUID, WorkItem]: ...


class TaskPlanRepository(Protocol):
    def save(self, plan: TaskPlan) -> TaskPlan: ...

    def get(self, plan_id: UUID) -> TaskPlan: ...

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        work_item_id: UUID,
        idempotency_key: str,
    ) -> TaskPlan | None: ...

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[TaskPlan]: ...


class ActionDraftRepository(Protocol):
    def save(self, draft: ActionDraft) -> ActionDraft: ...

    def get(self, draft_id: UUID) -> ActionDraft: ...

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[ActionDraft]: ...


class ApprovalRepository(Protocol):
    def save(self, approval: Approval) -> Approval: ...

    def get(self, approval_id: UUID) -> Approval: ...

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[Approval]: ...

    def list_pending(self, workspace_id: str) -> list[Approval]: ...


class PolicyDecisionRepository(Protocol):
    def add(self, decision: PolicyDecision) -> PolicyDecision: ...

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[PolicyDecision]: ...


class WorkflowEventRepository(Protocol):
    def add(self, event: WorkflowEvent) -> WorkflowEvent: ...

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[WorkflowEvent]: ...

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[WorkflowEvent]: ...


@dataclass
class InMemoryWorkItemRepository:
    records: dict[UUID, WorkItem] = field(default_factory=dict)

    def save(self, work_item: WorkItem) -> WorkItem:
        stored = deepcopy(work_item)
        self.records[work_item.id] = stored
        return deepcopy(stored)

    def get(self, work_item_id: UUID) -> WorkItem:
        try:
            return deepcopy(self.records[work_item_id])
        except KeyError as exc:
            raise NotFoundError(f"Work item not found: {work_item_id}") from exc

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> WorkItem | None:
        return deepcopy(
            next(
                (
                    item
                    for item in self.records.values()
                    if item.workspace_id == workspace_id and item.idempotency_key == idempotency_key
                ),
                None,
            )
        )

    def list_by_workspace(self, workspace_id: str) -> list[WorkItem]:
        return deepcopy(
            [item for item in self.records.values() if item.workspace_id == workspace_id]
        )

    def get_latest_for_documents(
        self,
        workspace_id: str,
        document_ids: list[UUID],
    ) -> dict[UUID, WorkItem]:
        requested = set(document_ids)
        latest: dict[UUID, WorkItem] = {}
        for item in self.records.values():
            if item.workspace_id != workspace_id:
                continue
            for document_id in item.linked_document_ids:
                if document_id not in requested:
                    continue
                existing = latest.get(document_id)
                if existing is None or item.updated_at > existing.updated_at:
                    latest[document_id] = item
        return deepcopy(latest)


@dataclass
class InMemoryTaskPlanRepository:
    records: dict[UUID, TaskPlan] = field(default_factory=dict)

    def save(self, plan: TaskPlan) -> TaskPlan:
        stored = deepcopy(plan)
        self.records[plan.id] = stored
        return deepcopy(stored)

    def get(self, plan_id: UUID) -> TaskPlan:
        try:
            return deepcopy(self.records[plan_id])
        except KeyError as exc:
            raise NotFoundError(f"Task plan not found: {plan_id}") from exc

    def get_by_idempotency_key(
        self,
        workspace_id: str,
        work_item_id: UUID,
        idempotency_key: str,
    ) -> TaskPlan | None:
        return deepcopy(
            next(
                (
                    plan
                    for plan in self.records.values()
                    if plan.workspace_id == workspace_id
                    and plan.work_item_id == work_item_id
                    and plan.idempotency_key == idempotency_key
                ),
                None,
            )
        )

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[TaskPlan]:
        return deepcopy(
            [
                plan
                for plan in self.records.values()
                if plan.workspace_id == workspace_id and plan.work_item_id == work_item_id
            ]
        )


@dataclass
class InMemoryActionDraftRepository:
    records: dict[UUID, ActionDraft] = field(default_factory=dict)

    def save(self, draft: ActionDraft) -> ActionDraft:
        stored = deepcopy(draft)
        self.records[draft.id] = stored
        return deepcopy(stored)

    def get(self, draft_id: UUID) -> ActionDraft:
        try:
            return deepcopy(self.records[draft_id])
        except KeyError as exc:
            raise NotFoundError(f"Action draft not found: {draft_id}") from exc

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[ActionDraft]:
        return deepcopy(
            [
                draft
                for draft in self.records.values()
                if draft.workspace_id == workspace_id and draft.work_item_id == work_item_id
            ]
        )


@dataclass
class InMemoryApprovalRepository:
    records: dict[UUID, Approval] = field(default_factory=dict)

    def save(self, approval: Approval) -> Approval:
        stored = deepcopy(approval)
        self.records[approval.id] = stored
        return deepcopy(stored)

    def get(self, approval_id: UUID) -> Approval:
        try:
            return deepcopy(self.records[approval_id])
        except KeyError as exc:
            raise NotFoundError(f"Approval not found: {approval_id}") from exc

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[Approval]:
        return deepcopy(
            [
                approval
                for approval in self.records.values()
                if approval.workspace_id == workspace_id and approval.work_item_id == work_item_id
            ]
        )

    def list_pending(self, workspace_id: str) -> list[Approval]:
        return deepcopy(
            [
                approval
                for approval in self.records.values()
                if approval.workspace_id == workspace_id and approval.status == "pending"
            ]
        )


@dataclass
class InMemoryPolicyDecisionRepository:
    records: list[PolicyDecision] = field(default_factory=list)

    def add(self, decision: PolicyDecision) -> PolicyDecision:
        stored = deepcopy(decision)
        self.records.append(stored)
        return deepcopy(stored)

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[PolicyDecision]:
        return deepcopy(
            [
                decision
                for decision in self.records
                if decision.workspace_id == workspace_id and decision.work_item_id == work_item_id
            ]
        )


@dataclass
class InMemoryWorkflowEventRepository:
    records: list[WorkflowEvent] = field(default_factory=list)

    def add(self, event: WorkflowEvent) -> WorkflowEvent:
        stored = deepcopy(event)
        self.records.append(stored)
        return deepcopy(stored)

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[WorkflowEvent]:
        return deepcopy(
            [
                event
                for event in self.records
                if event.workspace_id == workspace_id and event.document_id == document_id
            ]
        )

    def list_for_work_item(self, workspace_id: str, work_item_id: UUID) -> list[WorkflowEvent]:
        return deepcopy(
            [
                event
                for event in self.records
                if event.workspace_id == workspace_id and event.work_item_id == work_item_id
            ]
        )
