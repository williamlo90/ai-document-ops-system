from __future__ import annotations

import unittest
from uuid import uuid4

from app.backoffice.models import (
    ActionRiskLevel,
    ActionStepStatus,
    ActionType,
    WorkItem,
    WorkItemStatus,
    WorkType,
)
from app.backoffice.planner import PLANNER_VERSION, BackofficePlanner, PlanningInput
from app.core.security import SecurityContext


class BackofficePlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = BackofficePlanner()
        self.admin = SecurityContext(
            actor="admin",
            workspace_id="acme",
            role="admin",
            is_admin=True,
        )
        self.operator = SecurityContext(
            actor="operator",
            workspace_id="acme",
            role="operator",
        )

    def test_classifies_invoice_review_from_linked_document(self) -> None:
        work_item = WorkItem(workspace_id="acme", title="New invoice")
        work_item.link_document(uuid4())

        plan = self.planner.plan(work_item=work_item, context=self.operator)

        self.assertEqual(work_item.work_type, WorkType.INVOICE_REVIEW)
        self.assertEqual(work_item.status, WorkItemStatus.PLANNING)
        self.assertEqual(work_item.current_plan_id, plan.id)
        self.assertEqual(plan.planner_version, PLANNER_VERSION)
        self.assertEqual(plan.overall_confidence, "high")
        self.assertEqual(
            [step.action_type for step in plan.steps],
            [ActionType.EXPLAIN_DOCUMENT, ActionType.RECOMMEND_REVIEW],
        )

    def test_vendor_follow_up_plan_drafts_message_for_missing_fields(self) -> None:
        work_item = WorkItem(workspace_id="acme", title="Vendor invoice missing tax id")
        work_item.link_document(uuid4())

        plan = self.planner.plan(
            work_item=work_item,
            context=self.operator,
            planning_input=PlanningInput(missing_fields=("tax_id",)),
        )

        self.assertEqual(work_item.work_type, WorkType.VENDOR_FOLLOW_UP)
        self.assertEqual(plan.overall_confidence, "medium")
        self.assertEqual(plan.steps[-1].action_type, ActionType.DRAFT_VENDOR_MESSAGE)
        self.assertEqual(plan.steps[-1].risk_level, ActionRiskLevel.MEDIUM)
        self.assertFalse(plan.steps[-1].requires_approval)
        self.assertIn("tax_id", plan.steps[-1].why_this or "")

    def test_export_plan_waits_for_admin_confirmation_when_approved(self) -> None:
        work_item = WorkItem(
            workspace_id="acme",
            title="Export approved invoice",
            work_type=WorkType.INVOICE_EXPORT,
        )

        plan = self.planner.plan(
            work_item=work_item,
            context=self.admin,
            planning_input=PlanningInput(
                requested_outcome="export invoice",
                approved_for_export=True,
            ),
        )

        export_step = plan.steps[-1]
        self.assertEqual(export_step.action_type, ActionType.EXPORT_APPROVED_INVOICE)
        self.assertEqual(export_step.status, ActionStepStatus.WAITING_FOR_APPROVAL)
        self.assertEqual(export_step.risk_level, ActionRiskLevel.HIGH)
        self.assertTrue(export_step.requires_approval)
        self.assertIn("confirmation", export_step.why_not or "")

    def test_export_plan_blocks_when_invoice_is_not_approved(self) -> None:
        work_item = WorkItem(
            workspace_id="acme",
            title="Export invoice too early",
            work_type=WorkType.INVOICE_EXPORT,
        )

        plan = self.planner.plan(
            work_item=work_item,
            context=self.admin,
            planning_input=PlanningInput(requested_outcome="export invoice"),
        )

        export_step = plan.steps[-1]
        self.assertEqual(
            plan.escalation_reason, "Invoice export requires approved invoice evidence."
        )
        self.assertEqual(export_step.action_type, ActionType.EXPORT_APPROVED_INVOICE)
        self.assertEqual(export_step.status, ActionStepStatus.BLOCKED)
        self.assertEqual(export_step.why_not, "Invoice is not approved for export.")

    def test_low_confidence_plan_escalates_without_mutating_steps(self) -> None:
        work_item = WorkItem(workspace_id="acme", title="Unclear back-office request")

        plan = self.planner.plan(
            work_item=work_item,
            context=self.operator,
            planning_input=PlanningInput(evidence_sufficient=False),
        )

        self.assertEqual(work_item.work_type, WorkType.INSUFFICIENT_EVIDENCE)
        self.assertEqual(plan.overall_confidence, "low")
        self.assertTrue(plan.requires_human)
        self.assertEqual(plan.steps[0].action_type, ActionType.ESCALATE_TO_HUMAN)
        self.assertNotIn(ActionType.PROCESS_DOCUMENT, [step.action_type for step in plan.steps])

    def test_cross_workspace_context_creates_blocked_step(self) -> None:
        work_item = WorkItem(
            workspace_id="acme",
            title="Review invoice",
            work_type=WorkType.INVOICE_REVIEW,
        )
        work_item.link_document(uuid4())
        other_workspace_context = SecurityContext(
            actor="operator",
            workspace_id="other",
            role="operator",
        )

        plan = self.planner.plan(work_item=work_item, context=other_workspace_context)

        self.assertEqual(plan.steps[0].status, ActionStepStatus.BLOCKED)
        self.assertIn("workspace", plan.steps[0].why_not or "")

    def test_accounting_note_plan_is_draft_only(self) -> None:
        work_item = WorkItem(
            workspace_id="acme",
            title="Prepare accounting note",
            work_type=WorkType.ACCOUNTING_NOTE,
        )

        plan = self.planner.plan(work_item=work_item, context=self.operator)

        self.assertEqual(plan.steps[-1].action_type, ActionType.DRAFT_ACCOUNTING_NOTE)
        self.assertEqual(plan.steps[-1].risk_level, ActionRiskLevel.MEDIUM)
        self.assertEqual(plan.steps[-1].status, ActionStepStatus.PLANNED)
        self.assertIn("without external side effects", plan.steps[-1].why_this or "")


if __name__ == "__main__":
    unittest.main()
