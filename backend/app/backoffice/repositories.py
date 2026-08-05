from __future__ import annotations

from uuid import UUID

from app.backoffice.models import ApprovalRecord, TaskPlan, WorkItem


class BackofficeRepository:
    def __init__(self) -> None:
        self.work_items: dict[UUID, WorkItem] = {}
        self.plans: dict[UUID, TaskPlan] = {}
        self.approvals: dict[UUID, ApprovalRecord] = {}

    def add_work_item(self, item: WorkItem) -> None:
        self.work_items[item.id] = item

    def add_plan(self, plan: TaskPlan) -> None:
        self.plans[plan.id] = plan

    def add_approval(self, approval: ApprovalRecord) -> None:
        self.approvals[approval.id] = approval
