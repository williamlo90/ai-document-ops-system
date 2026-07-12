from __future__ import annotations

import unittest
from uuid import uuid4

from app.agentops.backoffice_scenarios import (
    DEFAULT_BACKOFFICE_SCENARIO_DATASET,
    evaluate_backoffice_scenario_plan,
    get_backoffice_scenario,
    load_backoffice_scenario_dataset,
)
from app.backoffice.models import WorkType
from app.backoffice.planner import PlanningInput
from app.backoffice.repositories import (
    InMemoryActionDraftRepository,
    InMemoryApprovalRepository,
    InMemoryPolicyDecisionRepository,
    InMemoryTaskPlanRepository,
    InMemoryWorkItemRepository,
)
from app.backoffice.services import BackofficeWorkflowService
from app.core.security import SecurityContext


class BackofficeScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_items = InMemoryWorkItemRepository()
        self.plans = InMemoryTaskPlanRepository()
        self.policy_decisions = InMemoryPolicyDecisionRepository()
        self.service = BackofficeWorkflowService(
            work_items=self.work_items,
            plans=self.plans,
            drafts=InMemoryActionDraftRepository(),
            approvals=InMemoryApprovalRepository(),
            policy_decisions=self.policy_decisions,
        )
        self.admin = SecurityContext(
            actor="admin",
            workspace_id="default",
            role="admin",
            is_admin=True,
        )
        self.operator = SecurityContext(
            actor="operator",
            workspace_id="default",
            role="operator",
        )

    def test_loads_project4_backoffice_scenario_dataset(self) -> None:
        dataset = load_backoffice_scenario_dataset(DEFAULT_BACKOFFICE_SCENARIO_DATASET)

        self.assertEqual(dataset.dataset_id, "project4_backoffice")
        self.assertEqual(dataset.dataset_version, "v1")
        self.assertEqual(len(dataset.scenarios), 5)
        self.assertEqual(dataset.scenarios[0].id, "invoice_review_read_only")
        self.assertEqual(dataset.scenarios[0].document_type, "invoice")
        self.assertEqual(dataset.scenarios[0].operation_type, "document_review")

    def test_evaluates_matched_confirm_execute_plan(self) -> None:
        dataset = load_backoffice_scenario_dataset(DEFAULT_BACKOFFICE_SCENARIO_DATASET)
        scenario = get_backoffice_scenario(dataset, "approved_invoice_export_confirmation")
        work_item = self.service.create_work_item(
            title=scenario.title,
            context=self.admin,
            work_type=WorkType(scenario.work_type),
            linked_document_ids=(uuid4(),),
        )

        result = self.service.plan_work_item(
            work_item_id=work_item.id,
            context=self.admin,
            planning_input=_planning_input(scenario.planning_input),
        )
        plan = self.plans.get(result.plan_id)
        policy_decisions = self.policy_decisions.list_for_work_item(
            work_item.workspace_id, work_item.id
        )

        evaluation = evaluate_backoffice_scenario_plan(
            dataset=dataset,
            scenario=scenario,
            work_item=work_item,
            plan=plan,
            policy_decisions=policy_decisions,
        )

        self.assertTrue(evaluation.passed)
        self.assertTrue(all(evaluation.checks.values()))
        self.assertTrue(evaluation.checks["document_type"])
        self.assertTrue(evaluation.checks["operation_type"])
        self.assertEqual(evaluation.actual_document_type, "invoice")
        self.assertEqual(evaluation.actual_operation_type, "document_export")
        self.assertEqual(
            evaluation.actual_plan_steps,
            ("inspect_queue", "export_approved_invoice"),
        )
        self.assertTrue(evaluation.actual_requires_human)

    def test_evaluates_mismatched_plan_steps(self) -> None:
        dataset = load_backoffice_scenario_dataset(DEFAULT_BACKOFFICE_SCENARIO_DATASET)
        scenario = get_backoffice_scenario(dataset, "approved_invoice_export_confirmation")
        work_item = self.service.create_work_item(
            title="Wrong scenario shape",
            context=self.operator,
            work_type=WorkType.INVOICE_REVIEW,
            linked_document_ids=(uuid4(),),
        )

        result = self.service.plan_work_item(work_item_id=work_item.id, context=self.operator)
        plan = self.plans.get(result.plan_id)
        policy_decisions = self.policy_decisions.list_for_work_item(
            work_item.workspace_id, work_item.id
        )

        evaluation = evaluate_backoffice_scenario_plan(
            dataset=dataset,
            scenario=scenario,
            work_item=work_item,
            plan=plan,
            policy_decisions=policy_decisions,
        )

        self.assertFalse(evaluation.passed)
        self.assertFalse(evaluation.checks["work_type"])
        self.assertFalse(evaluation.checks["plan_steps"])


def _planning_input(raw: dict[str, object]) -> PlanningInput:
    missing_fields = raw.get("missing_fields", ())
    return PlanningInput(
        requested_outcome=str(raw.get("requested_outcome") or ""),
        evidence_sufficient=bool(raw.get("evidence_sufficient")),
        approved_for_export=bool(raw.get("approved_for_export")),
        missing_fields=tuple(str(item) for item in missing_fields),
    )


if __name__ == "__main__":
    unittest.main()
