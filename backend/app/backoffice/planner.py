from __future__ import annotations

from app.backoffice.models import PlanStep, TaskPlan, WorkItem


def build_plan(work_item: WorkItem) -> TaskPlan:
    return TaskPlan(
        work_item_id=work_item.id,
        steps=(
            PlanStep("Review invoice evidence", consequential=False),
            PlanStep("Prepare approved invoice export", consequential=True),
        ),
        requires_approval=True,
    )
