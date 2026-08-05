from __future__ import annotations

from app.backoffice.models import ApprovalRecord, TaskPlan


class ExecutionNotAvailable(PermissionError):
    pass


def assert_planning_only(plan: TaskPlan, approval: ApprovalRecord | None = None) -> None:
    if any(step.execution_authority for step in plan.steps):
        raise ExecutionNotAvailable("M09 plans cannot execute")
    if approval is not None and approval.plan_id != plan.id:
        raise ValueError("Approval does not belong to plan")
