from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol
from uuid import UUID

from app.agent.contracts import AgentConfidence
from app.agent.models import AgentRun
from app.agent.repositories import AgentRunRepository
from app.backoffice.errors import BackofficeWorkflowError
from app.backoffice.execution import ACTION_TOOL_MAP
from app.backoffice.models import (
    ActionDraft,
    ActionStep,
    ActionStepStatus,
    ActionType,
    Approval,
    ApprovalStatus,
    DraftStatus,
    DraftType,
    TaskPlan,
    WorkItem,
    WorkItemStatus,
)
from app.backoffice.planner import BackofficePlanner, PlanningInput
from app.backoffice.policy import AutonomyPolicyEngine
from app.backoffice.repositories import (
    ActionDraftRepository,
    ApprovalRepository,
    PolicyDecisionRepository,
    TaskPlanRepository,
    WorkItemRepository,
)
from app.backoffice.request_identity import (
    normalized_key,
    planning_fingerprint,
    require_matching_fingerprint,
)
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.repositories import NotFoundError


class WorkflowEventRecorder(Protocol):
    def __call__(
        self,
        *,
        work_item: WorkItem,
        event_type: str,
        actor: str,
        summary: str,
        agent_run_id: UUID | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class BackofficePlanResult:
    work_item: WorkItem
    plan_id: UUID
    created_draft_ids: tuple[UUID, ...]
    pending_approval_ids: tuple[UUID, ...]


DRAFT_TYPE_MAP: dict[ActionType, DraftType] = {
    ActionType.DRAFT_ACCOUNTING_NOTE: DraftType.ACCOUNTING_NOTE,
    ActionType.DRAFT_VENDOR_MESSAGE: DraftType.VENDOR_MESSAGE,
    ActionType.EXPORT_APPROVED_INVOICE: DraftType.EXPORT_PREVIEW,
}


class BackofficePlanningService:
    def __init__(
        self,
        *,
        work_items: WorkItemRepository,
        plans: TaskPlanRepository,
        drafts: ActionDraftRepository,
        approvals: ApprovalRepository,
        policy_decisions: PolicyDecisionRepository,
        transactions: TransactionManager,
        record_event: WorkflowEventRecorder,
        planner: BackofficePlanner,
        policy: AutonomyPolicyEngine,
        agent_runs: AgentRunRepository | None,
    ) -> None:
        self.work_items = work_items
        self.plans = plans
        self.drafts = drafts
        self.approvals = approvals
        self.policy_decisions = policy_decisions
        self.transactions = transactions
        self.record_event = record_event
        self.planner = planner
        self.policy = policy
        self.agent_runs = agent_runs

    def plan_work_item(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        planning_input: PlanningInput | None = None,
        idempotency_key: str | None = None,
    ) -> BackofficePlanResult:
        key = normalized_key(idempotency_key)
        inputs = planning_input or PlanningInput()
        request_fingerprint = planning_fingerprint(inputs, context)
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            existing = self._existing_plan_result(
                work_item=work_item,
                context=context,
                key=key,
                request_fingerprint=request_fingerprint,
            )
            if existing is not None:
                return existing
            self.require_no_pending_execution(work_item)
            plan = self._generate_plan(
                work_item=work_item,
                context=context,
                planning_input=inputs,
                key=key,
                request_fingerprint=request_fingerprint,
            )
            draft_ids: list[UUID] = []
            approval_ids: list[UUID] = []
            for step in plan.steps:
                draft_id, approval_id = self._create_step_records(
                    work_item=work_item,
                    step=step,
                    context=context,
                )
                if draft_id is not None:
                    draft_ids.append(draft_id)
                if approval_id is not None:
                    approval_ids.append(approval_id)
            self._record_escalation(work_item, plan, context)
            return BackofficePlanResult(
                work_item=work_item,
                plan_id=plan.id,
                created_draft_ids=tuple(draft_ids),
                pending_approval_ids=tuple(approval_ids),
            )

    def _existing_plan_result(
        self,
        *,
        work_item: WorkItem,
        context: SecurityContext,
        key: str | None,
        request_fingerprint: str,
    ) -> BackofficePlanResult | None:
        if not key:
            return None
        existing_plan = self.plans.get_by_idempotency_key(
            context.workspace_id,
            work_item.id,
            key,
        )
        if existing_plan is None:
            return None
        require_matching_fingerprint(
            existing_plan.idempotency_fingerprint,
            request_fingerprint,
        )
        return self.plan_result_for(work_item, existing_plan, context.workspace_id)

    def _generate_plan(
        self,
        *,
        work_item: WorkItem,
        context: SecurityContext,
        planning_input: PlanningInput,
        key: str | None,
        request_fingerprint: str,
    ) -> TaskPlan:
        started = perf_counter()
        plan = self.planner.plan(
            work_item=work_item,
            context=context,
            planning_input=planning_input,
        )
        run = self.record_plan_run(
            work_item=work_item,
            plan=plan,
            context=context,
            latency_ms=(perf_counter() - started) * 1000,
        )
        if run is not None:
            plan.agent_run_id = run.id
        plan.idempotency_key = key
        plan.idempotency_fingerprint = request_fingerprint if key else None
        self.plans.save(plan)
        self.work_items.save(work_item)
        self.record_event(
            work_item=work_item,
            event_type="plan_generated",
            actor=context.actor,
            summary=f"Plan generated with {len(plan.steps)} bounded steps.",
            agent_run_id=run.id if run else None,
        )
        return plan

    def _create_step_records(
        self,
        *,
        work_item: WorkItem,
        step: ActionStep,
        context: SecurityContext,
    ) -> tuple[UUID | None, UUID | None]:
        decision = self.policy.decide(
            work_item=work_item,
            action_type=step.action_type,
            context=context,
            action_step_id=step.id,
            confirmed=not step.requires_approval,
        )
        self.policy_decisions.add(decision)
        draft_id = self._create_step_draft(work_item, step, context)
        approval_id = self._create_step_approval(work_item, step, context)
        return draft_id, approval_id

    def _create_step_draft(
        self,
        work_item: WorkItem,
        step: ActionStep,
        context: SecurityContext,
    ) -> UUID | None:
        if step.action_type not in DRAFT_TYPE_MAP or step.status == ActionStepStatus.BLOCKED:
            return None
        draft = self.create_draft_for_step(
            work_item_id=work_item.id,
            action_step=step,
            context=context,
        )
        self.record_event(
            work_item=work_item,
            event_type="draft_created",
            actor=context.actor,
            summary=f"Draft created: {draft.draft_type.value}.",
        )
        return draft.id

    def _create_step_approval(
        self,
        work_item: WorkItem,
        step: ActionStep,
        context: SecurityContext,
    ) -> UUID | None:
        if not step.requires_approval:
            return None
        approval = self.request_approval_for_step(
            work_item_id=work_item.id,
            action_step=step,
            context=context,
        )
        self.record_event(
            work_item=work_item,
            event_type="approval_requested",
            actor=context.actor,
            summary=f"Human approval requested for {step.action_type.value}.",
        )
        return approval.id

    def _record_escalation(
        self,
        work_item: WorkItem,
        plan: TaskPlan,
        context: SecurityContext,
    ) -> None:
        if not plan.escalation_reason:
            return
        work_item.status = WorkItemStatus.AWAITING_HUMAN
        self.work_items.save(work_item)
        self.record_event(
            work_item=work_item,
            event_type="workflow_escalated",
            actor=context.actor,
            summary=plan.escalation_reason,
        )

    def edit_draft(
        self,
        *,
        work_item_id: UUID,
        draft_id: UUID,
        context: SecurityContext,
        preview_content: str,
    ) -> ActionDraft:
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            draft = self.drafts.get(draft_id)
            if draft.workspace_id != context.workspace_id or draft.work_item_id != work_item.id:
                raise NotFoundError(f"Draft not found: {draft_id}")
            if draft.status != DraftStatus.DRAFTED:
                raise BackofficeWorkflowError("Only an active draft can be edited.")
            draft.preview_content = preview_content.strip()
            draft.updated_at = datetime.now(UTC)
            saved = self.drafts.save(draft)
            self.record_event(
                work_item=work_item,
                event_type="draft_edited",
                actor=context.actor,
                summary=f"Draft edited: {saved.draft_type.value}.",
            )
            return saved

    def regenerate_draft(
        self,
        *,
        work_item_id: UUID,
        draft_id: UUID,
        context: SecurityContext,
    ) -> ActionDraft:
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            previous = self.drafts.get(draft_id)
            if (
                previous.workspace_id != context.workspace_id
                or previous.work_item_id != work_item.id
            ):
                raise NotFoundError(f"Draft not found: {draft_id}")
            regenerated = ActionDraft(
                workspace_id=work_item.workspace_id,
                work_item_id=work_item.id,
                action_step_id=previous.action_step_id,
                draft_type=previous.draft_type,
                preview_content=(
                    f"{previous.preview_content}\n\nRegenerated for current work-item evidence."
                ),
            )
            saved = self.drafts.save(regenerated)
            self.record_event(
                work_item=work_item,
                event_type="draft_regenerated",
                actor=context.actor,
                summary=f"New draft version generated: {saved.draft_type.value}.",
            )
            return saved

    def create_draft_for_step(
        self,
        *,
        work_item_id: UUID,
        action_step: ActionStep,
        context: SecurityContext,
    ) -> ActionDraft:
        work_item = self._get_work_item_for_context(work_item_id, context)
        if action_step.status == ActionStepStatus.BLOCKED:
            raise BackofficeWorkflowError("Cannot create a draft for a blocked action.")
        try:
            draft_type = DRAFT_TYPE_MAP[action_step.action_type]
        except KeyError as exc:
            raise BackofficeWorkflowError(
                f"Action does not produce a reviewable draft: {action_step.action_type}"
            ) from exc
        draft = ActionDraft(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            action_step_id=action_step.id,
            draft_type=draft_type,
            preview_content=self.draft_preview(work_item, action_step, draft_type),
        )
        return self.drafts.save(draft)

    def request_approval_for_step(
        self,
        *,
        work_item_id: UUID,
        action_step: ActionStep,
        context: SecurityContext,
    ) -> Approval:
        work_item = self._get_work_item_for_context(work_item_id, context)
        if not action_step.requires_approval:
            raise BackofficeWorkflowError("This action does not require approval.")
        approval = Approval(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            action_step_id=action_step.id,
            requested_by=context.actor,
        )
        return self.approvals.save(approval)

    def approve_request(
        self,
        *,
        approval_id: UUID,
        context: SecurityContext,
        notes: str | None = None,
    ) -> Approval:
        with self.transactions.transaction():
            approval = self._get_approval_for_context(approval_id, context)
            already_approved = approval.status == ApprovalStatus.APPROVED
            approval.approve(context.actor, notes)
            saved = self.approvals.save(approval)
            if not already_approved:
                work_item = self._get_work_item_for_context(saved.work_item_id, context)
                self.record_event(
                    work_item=work_item,
                    event_type="approval_approved",
                    actor=context.actor,
                    summary=notes or "Human approval granted.",
                )
            return saved

    def reject_request(
        self,
        *,
        approval_id: UUID,
        context: SecurityContext,
        notes: str | None = None,
    ) -> Approval:
        with self.transactions.transaction():
            approval = self._get_approval_for_context(approval_id, context)
            already_rejected = approval.status == ApprovalStatus.REJECTED
            approval.reject(context.actor, notes)
            saved = self.approvals.save(approval)
            if not already_rejected:
                work_item = self._get_work_item_for_context(saved.work_item_id, context)
                self.record_event(
                    work_item=work_item,
                    event_type="approval_rejected",
                    actor=context.actor,
                    summary=notes or "Human approval rejected.",
                )
            return saved

    def plan_result_for(
        self,
        work_item: WorkItem,
        plan: TaskPlan,
        workspace_id: str,
    ) -> BackofficePlanResult:
        step_ids = {step.id for step in plan.steps}
        return BackofficePlanResult(
            work_item=work_item,
            plan_id=plan.id,
            created_draft_ids=tuple(
                draft.id
                for draft in self.drafts.list_for_work_item(
                    workspace_id,
                    work_item.id,
                )
                if draft.action_step_id in step_ids
            ),
            pending_approval_ids=tuple(
                approval.id
                for approval in self.approvals.list_for_work_item(
                    workspace_id,
                    work_item.id,
                )
                if approval.action_step_id in step_ids
            ),
        )

    @staticmethod
    def require_no_pending_execution(work_item: WorkItem) -> None:
        if work_item.business_context.get("execution_outcome") in {"in_flight", "unknown"}:
            raise BackofficeWorkflowError(
                "The active execution must be finalized or reconciled before replanning."
            )

    @staticmethod
    def draft_preview(
        work_item: WorkItem,
        action_step: ActionStep,
        draft_type: DraftType,
    ) -> str:
        if draft_type == DraftType.ACCOUNTING_NOTE:
            return (
                f"Accounting note draft for {work_item.title}: {action_step.why_this or ''}".strip()
            )
        if draft_type == DraftType.VENDOR_MESSAGE:
            return f"Vendor follow-up draft for {work_item.title}: {action_step.why_this or ''}".strip()
        return f"Export preview for {work_item.title}: {action_step.why_this or ''}".strip()

    def record_plan_run(
        self,
        *,
        work_item: WorkItem,
        plan: TaskPlan,
        context: SecurityContext,
        latency_ms: float,
    ) -> AgentRun | None:
        if self.agent_runs is None:
            return None
        confidence = {
            "high": AgentConfidence.HIGH,
            "medium": AgentConfidence.MEDIUM,
            "low": AgentConfidence.LOW,
        }.get(plan.overall_confidence, AgentConfidence.MEDIUM)
        selected = next(
            (
                ACTION_TOOL_MAP[step.action_type]
                for step in plan.steps
                if step.action_type in ACTION_TOOL_MAP
            ),
            None,
        )
        run = AgentRun(
            workspace_id=work_item.workspace_id,
            actor=context.actor,
            request=f"Plan work item {work_item.id}: {work_item.title}",
            intent="backoffice_plan_and_recommendation",
            prompt_version=plan.planner_version,
            confidence=confidence,
            selected_tool=selected,
            selection_reason=f"Generated {len(plan.steps)} policy-bounded steps.",
            human_escalation_reason=plan.escalation_reason,
            final_summary=f"Plan {plan.id} generated with {len(plan.steps)} steps.",
            work_item_id=work_item.id,
            plan_id=plan.id,
            latency_ms=latency_ms,
        )
        for step in plan.steps:
            if step.status == ActionStepStatus.BLOCKED:
                run.block_action(step.why_not or f"{step.action_type.value} blocked")
        return self.agent_runs.add(run)

    def _get_work_item_for_context(
        self,
        work_item_id: UUID,
        context: SecurityContext,
    ) -> WorkItem:
        work_item = self.work_items.get(work_item_id)
        if work_item.workspace_id != context.workspace_id:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        return work_item

    def _get_approval_for_context(
        self,
        approval_id: UUID,
        context: SecurityContext,
    ) -> Approval:
        approval = self.approvals.get(approval_id)
        if approval.workspace_id != context.workspace_id:
            raise NotFoundError(f"Approval not found: {approval_id}")
        return approval
