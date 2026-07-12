from __future__ import annotations

import unittest
from uuid import uuid4

from app.agent.contracts import AgentConfidence, AgentToolName, AgentToolResponse, AgentToolRisk
from app.agent.tools import ToolExecutionRequest
from app.backoffice.models import (
    ActionStepStatus,
    ActionType,
    ApprovalStatus,
    DraftType,
    WorkItemStatus,
    WorkType,
)
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
from app.documents.models import DocumentRecord
from app.documents.repositories import InMemoryDocumentRepository, NotFoundError
from app.documents.status import DocumentStatus


class FakeToolExecutor:
    def __init__(self) -> None:
        self.requests: list[ToolExecutionRequest] = []

    def execute(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        self.requests.append(request)
        return AgentToolResponse(
            tool_name=request.tool_name,
            status="success",
            risk=AgentToolRisk.ADMIN_ACTION,
            summary=f"Executed {request.tool_name.value}",
            confidence=AgentConfidence.HIGH,
            evidence=(f"workspace_id={context.workspace_id}",),
        )


class BackofficeWorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = FakeToolExecutor()
        self.work_items = InMemoryWorkItemRepository()
        self.plans = InMemoryTaskPlanRepository()
        self.drafts = InMemoryActionDraftRepository()
        self.approvals = InMemoryApprovalRepository()
        self.decisions = InMemoryPolicyDecisionRepository()
        self.documents = InMemoryDocumentRepository()
        self.service = BackofficeWorkflowService(
            work_items=self.work_items,
            plans=self.plans,
            drafts=self.drafts,
            approvals=self.approvals,
            policy_decisions=self.decisions,
            tool_executor=self.executor,
            documents=self.documents,
        )
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

    def test_create_and_plan_are_idempotent_when_key_is_replayed(self) -> None:
        first_item = self.service.create_work_item(
            title="Export approved invoice",
            context=self.admin,
            work_type=WorkType.INVOICE_EXPORT,
            linked_document_ids=(uuid4(),),
            idempotency_key="create-export-1",
        )
        second_item = self.service.create_work_item(
            title="Duplicate request must not create another item",
            context=self.admin,
            work_type=WorkType.INVOICE_EXPORT,
            idempotency_key="create-export-1",
        )
        planning_input = PlanningInput(
            requested_outcome="export invoice",
            approved_for_export=True,
        )
        first_plan = self.service.plan_work_item(
            work_item_id=first_item.id,
            context=self.admin,
            planning_input=planning_input,
            idempotency_key="plan-export-1",
        )
        second_plan = self.service.plan_work_item(
            work_item_id=first_item.id,
            context=self.admin,
            planning_input=planning_input,
            idempotency_key="plan-export-1",
        )

        self.assertEqual(second_item.id, first_item.id)
        self.assertEqual(second_plan.plan_id, first_plan.plan_id)
        self.assertEqual(len(self.work_items.records), 1)
        self.assertEqual(len(self.plans.records), 1)
        self.assertEqual(len(self.drafts.records), 1)
        self.assertEqual(len(self.approvals.records), 1)

    def test_plan_work_item_creates_reviewable_vendor_message_draft(self) -> None:
        work_item = self.service.create_work_item(
            title="Vendor invoice missing tax id",
            context=self.operator,
            linked_document_ids=(uuid4(),),
        )

        result = self.service.plan_work_item(
            work_item_id=work_item.id,
            context=self.operator,
            planning_input=PlanningInput(missing_fields=("tax_id",)),
        )

        self.assertEqual(len(result.created_draft_ids), 1)
        self.assertEqual(result.pending_approval_ids, ())
        draft = self.drafts.get(result.created_draft_ids[0])
        self.assertEqual(draft.draft_type, DraftType.VENDOR_MESSAGE)
        self.assertIn("tax_id", draft.preview_content)
        self.assertEqual(self.executor.requests, [])

    def test_plan_work_item_creates_export_preview_and_pending_approval(self) -> None:
        work_item = self.service.create_work_item(
            title="Export approved invoice",
            context=self.admin,
            work_type=WorkType.INVOICE_EXPORT,
            linked_document_ids=(uuid4(),),
        )

        result = self.service.plan_work_item(
            work_item_id=work_item.id,
            context=self.admin,
            planning_input=PlanningInput(
                requested_outcome="export invoice",
                approved_for_export=True,
            ),
        )

        self.assertEqual(len(result.created_draft_ids), 1)
        self.assertEqual(len(result.pending_approval_ids), 1)
        draft = self.drafts.get(result.created_draft_ids[0])
        approval = self.approvals.get(result.pending_approval_ids[0])
        self.assertEqual(draft.draft_type, DraftType.EXPORT_PREVIEW)
        self.assertEqual(approval.status, ApprovalStatus.PENDING)
        self.assertGreaterEqual(len(self.decisions.records), 1)

    def test_execution_is_blocked_until_human_approval_exists(self) -> None:
        work_item, export_step_id, _approval_id = self._planned_export()

        response = self.service.execute_approved_step(
            work_item_id=work_item.id,
            action_step_id=export_step_id,
            context=self.admin,
        )

        self.assertEqual(response.status, "blocked")
        self.assertEqual(self.executor.requests, [])

    def test_approved_high_risk_action_executes_through_controlled_executor(self) -> None:
        work_item, export_step_id, approval_id = self._planned_export(
            document_id=self._document(status=DocumentStatus.APPROVED).id
        )
        self.service.approve_request(
            approval_id=approval_id,
            context=self.admin,
            notes="Approved for demo export.",
        )

        response = self.service.execute_approved_step(
            work_item_id=work_item.id,
            action_step_id=export_step_id,
            context=self.admin,
        )

        self.assertEqual(response.status, "success")
        self.assertEqual(self.executor.requests[0].tool_name, AgentToolName.EXPORT_APPROVED_CSV)
        self.assertTrue(self.executor.requests[0].confirmed)
        self.assertEqual(self.work_items.get(work_item.id).status, WorkItemStatus.RESOLVED)
        plan = self.plans.get(work_item.current_plan_id)
        self.assertEqual(plan.steps[-1].status, ActionStepStatus.EXECUTED)

        replay = self.service.execute_approved_step(
            work_item_id=work_item.id,
            action_step_id=export_step_id,
            context=self.admin,
        )
        self.assertEqual(replay.status, "success")
        self.assertEqual(len(self.executor.requests), 1)

    def test_export_execution_rechecks_linked_invoice_approval(self) -> None:
        document = self._document(status=DocumentStatus.NEEDS_REVIEW)
        work_item, export_step_id, approval_id = self._planned_export(document_id=document.id)
        self.service.approve_request(
            approval_id=approval_id,
            context=self.admin,
            notes="Approved stale plan.",
        )

        response = self.service.execute_approved_step(
            work_item_id=work_item.id,
            action_step_id=export_step_id,
            context=self.admin,
        )

        self.assertEqual(response.status, "blocked")
        self.assertIn("approved first", response.summary)
        self.assertEqual(self.executor.requests, [])
        self.assertNotEqual(self.work_items.get(work_item.id).status, WorkItemStatus.RESOLVED)

    def test_approval_replay_is_safe_but_opposite_decision_is_rejected(self) -> None:
        _work_item, _step_id, approval_id = self._planned_export()
        first = self.service.approve_request(
            approval_id=approval_id,
            context=self.admin,
            notes="Approved once.",
        )
        replay = self.service.approve_request(
            approval_id=approval_id,
            context=self.admin,
            notes="Duplicate request.",
        )

        self.assertEqual(replay.status, ApprovalStatus.APPROVED)
        self.assertEqual(replay.reviewed_at, first.reviewed_at)
        with self.assertRaises(ValueError):
            self.service.reject_request(
                approval_id=approval_id,
                context=self.admin,
                notes="Conflicting decision.",
            )

    def test_cross_workspace_work_item_is_not_visible(self) -> None:
        work_item = self.service.create_work_item(
            title="Acme private work",
            context=self.admin,
            work_type=WorkType.ACCOUNTING_NOTE,
        )
        other_context = SecurityContext(
            actor="admin", workspace_id="other", role="admin", is_admin=True
        )

        with self.assertRaises(NotFoundError):
            self.service.plan_work_item(work_item_id=work_item.id, context=other_context)

    def test_rejected_approval_does_not_execute(self) -> None:
        work_item, export_step_id, approval_id = self._planned_export()
        self.service.reject_request(
            approval_id=approval_id,
            context=self.admin,
            notes="Not ready.",
        )

        response = self.service.execute_approved_step(
            work_item_id=work_item.id,
            action_step_id=export_step_id,
            context=self.admin,
        )

        self.assertEqual(response.status, "blocked")
        self.assertEqual(self.executor.requests, [])

    def _planned_export(self, document_id=None):
        work_item = self.service.create_work_item(
            title="Export approved invoice",
            context=self.admin,
            work_type=WorkType.INVOICE_EXPORT,
            linked_document_ids=(document_id or uuid4(),),
        )
        result = self.service.plan_work_item(
            work_item_id=work_item.id,
            context=self.admin,
            planning_input=PlanningInput(
                requested_outcome="export invoice",
                approved_for_export=True,
            ),
        )
        plan = self.plans.get(result.plan_id)
        export_step = next(
            step for step in plan.steps if step.action_type == ActionType.EXPORT_APPROVED_INVOICE
        )
        return work_item, export_step.id, result.pending_approval_ids[0]

    def _document(self, status: DocumentStatus) -> DocumentRecord:
        return self.documents.add(
            DocumentRecord(
                original_filename="invoice.pdf",
                storage_key=f"uploads/{uuid4()}.pdf",
                content_type="application/pdf",
                workspace_id=self.admin.workspace_id,
                status=status,
            )
        )


if __name__ == "__main__":
    unittest.main()
