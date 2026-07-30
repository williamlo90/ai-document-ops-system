from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.backoffice.errors import BackofficeWorkflowError
from app.backoffice.execution import EXECUTION_LEASE_SECONDS, WorkflowEventRecorder
from app.backoffice.models import ActionStep, ActionStepStatus, TaskPlan, WorkItem, WorkItemStatus
from app.backoffice.repositories import TaskPlanRepository, WorkItemRepository
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.repositories import NotFoundError


class BackofficeExecutionRecovery:
    def __init__(
        self,
        *,
        work_items: WorkItemRepository,
        plans: TaskPlanRepository,
        transactions: TransactionManager,
        record_event: WorkflowEventRecorder,
    ) -> None:
        self.work_items = work_items
        self.plans = plans
        self.transactions = transactions
        self.record_event = record_event

    def reconcile_execution(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
        succeeded: bool,
        summary: str,
    ) -> WorkItem:
        normalized_summary = " ".join(summary.split())[:500]
        if not normalized_summary:
            raise BackofficeWorkflowError("A reconciliation summary is required.")
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            plan = self.plan_containing_step(work_item, action_step_id)
            step = self._find_step(plan.steps, action_step_id)
            if step.status == ActionStepStatus.EXECUTED:
                if succeeded:
                    return work_item
                raise BackofficeWorkflowError("A successful reconciliation cannot be overwritten.")
            if step.status == ActionStepStatus.FAILED:
                if not succeeded:
                    return work_item
                raise BackofficeWorkflowError("A failed reconciliation cannot be overwritten.")
            if step.status != ActionStepStatus.EXECUTING:
                raise BackofficeWorkflowError(
                    "Only an execution with an unknown outcome can be reconciled."
                )
            if not self.execution_target_matches(work_item, plan.id, step.id):
                raise BackofficeWorkflowError(
                    "The execution target does not match the active reservation."
                )
            if not self._execution_is_reconcilable(work_item):
                raise BackofficeWorkflowError(
                    "An active execution cannot be reconciled before its outcome is unknown."
                )

            now = datetime.now(UTC)
            step.status = ActionStepStatus.EXECUTED if succeeded else ActionStepStatus.FAILED
            step.updated_at = now
            work_item.status = WorkItemStatus.RESOLVED if succeeded else WorkItemStatus.FAILED
            work_item.attach_context(
                "execution_outcome",
                "confirmed_success" if succeeded else "confirmed_failure",
            )
            work_item.updated_at = now
            self.plans.save(plan)
            self.work_items.save(work_item)
            self.record_event(
                work_item=work_item,
                event_type=(
                    "action_execution_reconciled_succeeded"
                    if succeeded
                    else "action_execution_reconciled_failed"
                ),
                actor=context.actor,
                summary=normalized_summary,
            )
            return work_item

    def plan_containing_step(self, work_item: WorkItem, step_id: UUID) -> TaskPlan:
        preferred_ids = self._execution_plan_ids(work_item)
        for plan_id in preferred_ids:
            plan = self.plans.get(plan_id)
            if plan.workspace_id != work_item.workspace_id or plan.work_item_id != work_item.id:
                raise BackofficeWorkflowError("Execution plan does not belong to this work item.")
            if any(step.id == step_id for step in plan.steps):
                return plan
        for plan in self.plans.list_for_work_item(work_item.workspace_id, work_item.id):
            if any(step.id == step_id for step in plan.steps):
                return plan
        raise NotFoundError(f"Action step not found: {step_id}")

    @staticmethod
    def execution_target_matches(
        work_item: WorkItem,
        plan_id: UUID,
        step_id: UUID,
    ) -> bool:
        return work_item.business_context.get("execution_plan_id") == str(
            plan_id
        ) and work_item.business_context.get("execution_step_id") == str(step_id)

    @staticmethod
    def _find_step(steps: tuple[ActionStep, ...], step_id: UUID) -> ActionStep:
        for step in steps:
            if step.id == step_id:
                return step
        raise NotFoundError(f"Action step not found: {step_id}")

    def _get_work_item_for_context(
        self,
        work_item_id: UUID,
        context: SecurityContext,
    ) -> WorkItem:
        work_item = self.work_items.get(work_item_id)
        if work_item.workspace_id != context.workspace_id:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        return work_item

    @staticmethod
    def _execution_is_reconcilable(work_item: WorkItem) -> bool:
        outcome = work_item.business_context.get("execution_outcome")
        if outcome == "unknown":
            return True
        if outcome != "in_flight":
            return False
        heartbeat_value = work_item.business_context.get("execution_heartbeat_at")
        if not heartbeat_value:
            return True
        try:
            heartbeat_at = datetime.fromisoformat(heartbeat_value)
        except ValueError:
            return False
        if heartbeat_at.tzinfo is None:
            return False
        return datetime.now(UTC) - heartbeat_at.astimezone(UTC) >= timedelta(
            seconds=EXECUTION_LEASE_SECONDS
        )

    @staticmethod
    def _execution_plan_ids(work_item: WorkItem) -> tuple[UUID, ...]:
        candidates = (
            work_item.business_context.get("execution_plan_id"),
            str(work_item.current_plan_id) if work_item.current_plan_id else None,
        )
        result: list[UUID] = []
        for candidate in candidates:
            if not candidate:
                continue
            try:
                plan_id = UUID(candidate)
            except ValueError as exc:
                raise BackofficeWorkflowError("Execution plan identifier is invalid.") from exc
            if plan_id not in result:
                result.append(plan_id)
        return tuple(result)
