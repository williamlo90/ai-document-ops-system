from __future__ import annotations

import unittest
from uuid import uuid4

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
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkType,
)
from app.backoffice.repositories import (
    InMemoryActionDraftRepository,
    InMemoryApprovalRepository,
    InMemoryPolicyDecisionRepository,
    InMemoryTaskPlanRepository,
    InMemoryWorkItemRepository,
)


class BackofficeDomainModelTests(unittest.TestCase):
    def test_work_item_can_be_classified_linked_and_contextualized(self) -> None:
        document_id = uuid4()
        work_item = WorkItem(workspace_id="acme", title="Invoice from Vendor A")

        work_item.classify(WorkType.INVOICE_REVIEW, WorkItemPriority.HIGH)
        work_item.link_document(document_id)
        work_item.attach_context("vendor", "Vendor A")

        self.assertEqual(work_item.status, WorkItemStatus.CLASSIFIED)
        self.assertEqual(work_item.work_type, WorkType.INVOICE_REVIEW)
        self.assertEqual(work_item.priority, WorkItemPriority.HIGH)
        self.assertEqual(work_item.linked_document_ids, (document_id,))
        self.assertEqual(work_item.business_context["vendor"], "Vendor A")

    def test_task_plan_records_steps_risk_and_human_need(self) -> None:
        work_item = WorkItem(workspace_id="acme", title="Review invoice")
        plan = TaskPlan(
            workspace_id="acme",
            work_item_id=work_item.id,
            planner_version="deterministic-backoffice-v1",
        )
        plan.add_step(
            ActionStep(
                action_type=ActionType.DRAFT_VENDOR_MESSAGE,
                risk_level=ActionRiskLevel.MEDIUM,
                requires_approval=True,
                why_this="Missing tax id requires vendor clarification.",
            )
        )
        work_item.set_current_plan(plan.id)

        self.assertEqual(work_item.current_plan_id, plan.id)
        self.assertEqual(work_item.status, WorkItemStatus.PLANNING)
        self.assertTrue(plan.requires_human)
        self.assertEqual(plan.steps[0].risk_level, ActionRiskLevel.MEDIUM)

    def test_action_step_can_wait_for_approval_or_block(self) -> None:
        step = ActionStep(
            action_type=ActionType.EXPORT_APPROVED_INVOICE,
            risk_level=ActionRiskLevel.HIGH,
            tool_name="export_approved_invoices",
            requires_approval=True,
        )

        step.mark_waiting_for_approval()
        self.assertEqual(step.status, ActionStepStatus.WAITING_FOR_APPROVAL)

        step.block("Invoice is not approved yet.")
        self.assertEqual(step.status, ActionStepStatus.BLOCKED)
        self.assertEqual(step.why_not, "Invoice is not approved yet.")

    def test_draft_and_approval_statuses_are_explicit(self) -> None:
        work_item_id = uuid4()
        draft = ActionDraft(
            workspace_id="acme",
            work_item_id=work_item_id,
            draft_type=DraftType.ACCOUNTING_NOTE,
            preview_content="Post approved invoice to AP queue.",
        )
        approval = Approval(
            workspace_id="acme",
            work_item_id=work_item_id,
            requested_by="operator",
            draft_id=draft.id,
        )

        draft.approve()
        approval.approve("finance-lead", "Looks correct.")

        self.assertEqual(draft.status, DraftStatus.APPROVED)
        self.assertEqual(approval.status, ApprovalStatus.APPROVED)
        self.assertEqual(approval.reviewed_by, "finance-lead")

    def test_policy_decision_is_auditable_domain_record(self) -> None:
        decision = PolicyDecision(
            workspace_id="acme",
            work_item_id=uuid4(),
            action_type=ActionType.EXPORT_APPROVED_INVOICE,
            autonomy_level=AutonomyLevel.CONFIRM_EXECUTE,
            risk_level=ActionRiskLevel.HIGH,
            allowed=True,
            requires_confirmation=True,
            reason="Export is high risk and requires explicit operator confirmation.",
        )

        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual(decision.autonomy_level, AutonomyLevel.CONFIRM_EXECUTE)


class BackofficeRepositoryTests(unittest.TestCase):
    def test_work_items_are_workspace_scoped(self) -> None:
        repository = InMemoryWorkItemRepository()
        acme = repository.save(WorkItem(workspace_id="acme", title="Acme invoice"))
        repository.save(WorkItem(workspace_id="other", title="Other invoice"))

        self.assertEqual(repository.get(acme.id), acme)
        self.assertEqual(repository.list_by_workspace("acme"), [acme])

    def test_plans_drafts_approvals_and_decisions_are_workspace_scoped(self) -> None:
        work_item_id = uuid4()
        plan_repo = InMemoryTaskPlanRepository()
        draft_repo = InMemoryActionDraftRepository()
        approval_repo = InMemoryApprovalRepository()
        decision_repo = InMemoryPolicyDecisionRepository()

        acme_plan = plan_repo.save(
            TaskPlan(
                workspace_id="acme",
                work_item_id=work_item_id,
                planner_version="deterministic-backoffice-v1",
            )
        )
        plan_repo.save(
            TaskPlan(
                workspace_id="other",
                work_item_id=work_item_id,
                planner_version="deterministic-backoffice-v1",
            )
        )
        acme_draft = draft_repo.save(
            ActionDraft(
                workspace_id="acme",
                work_item_id=work_item_id,
                draft_type=DraftType.VENDOR_MESSAGE,
                preview_content="Please send the tax id.",
            )
        )
        draft_repo.save(
            ActionDraft(
                workspace_id="other",
                work_item_id=work_item_id,
                draft_type=DraftType.VENDOR_MESSAGE,
                preview_content="Other workspace draft.",
            )
        )
        acme_approval = approval_repo.save(
            Approval(workspace_id="acme", work_item_id=work_item_id, requested_by="operator")
        )
        approval_repo.save(
            Approval(workspace_id="other", work_item_id=work_item_id, requested_by="operator")
        )
        acme_decision = decision_repo.add(
            PolicyDecision(
                workspace_id="acme",
                work_item_id=work_item_id,
                action_type=ActionType.DRAFT_VENDOR_MESSAGE,
                autonomy_level=AutonomyLevel.DRAFT,
                risk_level=ActionRiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason="Draft-only action has no external side effect.",
            )
        )
        decision_repo.add(
            PolicyDecision(
                workspace_id="other",
                work_item_id=work_item_id,
                action_type=ActionType.DRAFT_VENDOR_MESSAGE,
                autonomy_level=AutonomyLevel.DRAFT,
                risk_level=ActionRiskLevel.MEDIUM,
                allowed=True,
                requires_confirmation=False,
                reason="Other workspace decision.",
            )
        )

        self.assertEqual(plan_repo.list_for_work_item("acme", work_item_id), [acme_plan])
        self.assertEqual(draft_repo.list_for_work_item("acme", work_item_id), [acme_draft])
        self.assertEqual(approval_repo.list_pending("acme"), [acme_approval])
        self.assertEqual(decision_repo.list_for_work_item("acme", work_item_id), [acme_decision])


if __name__ == "__main__":
    unittest.main()
