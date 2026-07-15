from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol
from uuid import UUID

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    AgentToolRisk,
)
from app.agent.models import AgentRun, AgentToolCallTrace
from app.agent.repositories import AgentRunRepository
from app.agent.tools import ToolExecutionRequest
from app.backoffice.models import (
    ActionDraft,
    ActionStep,
    ActionStepStatus,
    ActionType,
    Approval,
    ApprovalStatus,
    DraftStatus,
    DraftType,
    WorkflowEvent,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkType,
)
from app.backoffice.planner import BackofficePlanner, PlanningInput
from app.backoffice.policy import AutonomyPolicyEngine
from app.backoffice.repositories import (
    ActionDraftRepository,
    ApprovalRepository,
    PolicyDecisionRepository,
    TaskPlanRepository,
    WorkItemRepository,
    WorkflowEventRepository,
)
from app.core.security import SecurityContext
from app.documents.repositories import DocumentRepository, NotFoundError
from app.documents.status import DocumentStatus


class BackofficeWorkflowError(ValueError):
    pass


class BackofficeToolExecutor(Protocol):
    def execute(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse: ...


@dataclass(frozen=True)
class BackofficePlanResult:
    work_item: WorkItem
    plan_id: UUID
    created_draft_ids: tuple[UUID, ...]
    pending_approval_ids: tuple[UUID, ...]


ACTION_TOOL_MAP: dict[ActionType, AgentToolName] = {
    ActionType.PROCESS_DOCUMENT: AgentToolName.PROCESS_DOCUMENT,
    ActionType.EXPORT_APPROVED_INVOICE: AgentToolName.EXPORT_APPROVED_CSV,
}


DRAFT_TYPE_MAP: dict[ActionType, DraftType] = {
    ActionType.DRAFT_ACCOUNTING_NOTE: DraftType.ACCOUNTING_NOTE,
    ActionType.DRAFT_VENDOR_MESSAGE: DraftType.VENDOR_MESSAGE,
    ActionType.EXPORT_APPROVED_INVOICE: DraftType.EXPORT_PREVIEW,
}


class BackofficeWorkflowService:
    def __init__(
        self,
        *,
        work_items: WorkItemRepository,
        plans: TaskPlanRepository,
        drafts: ActionDraftRepository,
        approvals: ApprovalRepository,
        policy_decisions: PolicyDecisionRepository,
        workflow_events: WorkflowEventRepository | None = None,
        planner: BackofficePlanner | None = None,
        policy: AutonomyPolicyEngine | None = None,
        tool_executor: BackofficeToolExecutor | None = None,
        agent_runs: AgentRunRepository | None = None,
        documents: DocumentRepository | None = None,
    ) -> None:
        self.work_items = work_items
        self.plans = plans
        self.drafts = drafts
        self.approvals = approvals
        self.policy_decisions = policy_decisions
        self.workflow_events = workflow_events
        self.policy = policy or AutonomyPolicyEngine()
        self.planner = planner or BackofficePlanner(policy=self.policy)
        self.tool_executor = tool_executor
        self.agent_runs = agent_runs
        self.documents = documents

    def create_work_item(
        self,
        *,
        title: str,
        context: SecurityContext,
        work_type: WorkType | None = None,
        linked_document_ids: tuple[UUID, ...] = (),
        business_context: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> WorkItem:
        normalized_key = _normalized_key(idempotency_key)
        if normalized_key:
            existing = next(
                (
                    item
                    for item in self.work_items.list_by_workspace(context.workspace_id)
                    if item.idempotency_key == normalized_key
                ),
                None,
            )
            if existing is not None:
                return existing
        work_item = WorkItem(
            workspace_id=context.workspace_id,
            title=title,
            work_type=work_type,
            linked_document_ids=linked_document_ids,
            business_context=dict(business_context or {}),
            idempotency_key=normalized_key,
        )
        if work_type is not None:
            work_item.classify(work_type)
        saved = self.work_items.save(work_item)
        self._record_event(
            work_item=saved,
            event_type="work_item_created",
            actor=context.actor,
            summary=f"Work item created: {saved.title}",
        )
        return saved

    def plan_work_item(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        planning_input: PlanningInput | None = None,
        idempotency_key: str | None = None,
    ) -> BackofficePlanResult:
        work_item = self._get_work_item_for_context(work_item_id, context)
        normalized_key = _normalized_key(idempotency_key)
        if normalized_key:
            existing_plan = next(
                (
                    plan
                    for plan in self.plans.list_for_work_item(context.workspace_id, work_item.id)
                    if plan.idempotency_key == normalized_key
                ),
                None,
            )
            if existing_plan is not None:
                step_ids = {step.id for step in existing_plan.steps}
                return BackofficePlanResult(
                    work_item=work_item,
                    plan_id=existing_plan.id,
                    created_draft_ids=tuple(
                        draft.id
                        for draft in self.drafts.list_for_work_item(
                            context.workspace_id, work_item.id
                        )
                        if draft.action_step_id in step_ids
                    ),
                    pending_approval_ids=tuple(
                        approval.id
                        for approval in self.approvals.list_for_work_item(
                            context.workspace_id, work_item.id
                        )
                        if approval.action_step_id in step_ids
                    ),
                )
        started = perf_counter()
        plan = self.planner.plan(
            work_item=work_item,
            context=context,
            planning_input=planning_input,
        )
        run = self._record_plan_run(
            work_item=work_item,
            plan=plan,
            context=context,
            latency_ms=(perf_counter() - started) * 1000,
        )
        if run is not None:
            plan.agent_run_id = run.id
        plan.idempotency_key = normalized_key
        self.plans.save(plan)
        self.work_items.save(work_item)
        self._record_event(
            work_item=work_item,
            event_type="plan_generated",
            actor=context.actor,
            summary=f"Plan generated with {len(plan.steps)} bounded steps.",
            agent_run_id=run.id if run else None,
        )

        draft_ids: list[UUID] = []
        approval_ids: list[UUID] = []
        for step in plan.steps:
            decision = self.policy.decide(
                work_item=work_item,
                action_type=step.action_type,
                context=context,
                action_step_id=step.id,
                confirmed=not step.requires_approval,
            )
            self.policy_decisions.add(decision)

            if step.action_type in DRAFT_TYPE_MAP and step.status != ActionStepStatus.BLOCKED:
                draft = self.create_draft_for_step(
                    work_item_id=work_item.id,
                    action_step=step,
                    context=context,
                )
                draft_ids.append(draft.id)
                self._record_event(
                    work_item=work_item,
                    event_type="draft_created",
                    actor=context.actor,
                    summary=f"Draft created: {draft.draft_type.value}.",
                )

            if step.requires_approval:
                approval = self.request_approval_for_step(
                    work_item_id=work_item.id,
                    action_step=step,
                    context=context,
                )
                approval_ids.append(approval.id)
                self._record_event(
                    work_item=work_item,
                    event_type="approval_requested",
                    actor=context.actor,
                    summary=f"Human approval requested for {step.action_type.value}.",
                )

        if plan.escalation_reason:
            work_item.status = WorkItemStatus.AWAITING_HUMAN
            self.work_items.save(work_item)
            self._record_event(
                work_item=work_item,
                event_type="workflow_escalated",
                actor=context.actor,
                summary=plan.escalation_reason,
            )
        return BackofficePlanResult(
            work_item=work_item,
            plan_id=plan.id,
            created_draft_ids=tuple(draft_ids),
            pending_approval_ids=tuple(approval_ids),
        )

    def update_work_item(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        title: str | None = None,
        priority: WorkItemPriority | None = None,
        assignee: str | None = None,
        requested_outcome: str | None = None,
        tags: tuple[str, ...] | None = None,
    ) -> WorkItem:
        work_item = self._get_work_item_for_context(work_item_id, context)
        if title is not None:
            work_item.title = title.strip() or work_item.title
        if priority is not None:
            work_item.priority = priority
        if assignee is not None:
            work_item.business_context["assignee"] = assignee.strip()
        if requested_outcome is not None:
            work_item.business_context["requested_outcome"] = requested_outcome.strip()
        if tags is not None:
            work_item.business_context["tags"] = ",".join(
                dict.fromkeys(tag.strip() for tag in tags if tag.strip())
            )
        work_item.updated_at = datetime.now(UTC)
        saved = self.work_items.save(work_item)
        self._record_event(
            work_item=saved,
            event_type="work_item_updated",
            actor=context.actor,
            summary="Work item ownership and operational metadata updated.",
        )
        return saved

    def edit_draft(
        self,
        *,
        work_item_id: UUID,
        draft_id: UUID,
        context: SecurityContext,
        preview_content: str,
    ) -> ActionDraft:
        work_item = self._get_work_item_for_context(work_item_id, context)
        draft = self.drafts.get(draft_id)
        if draft.workspace_id != context.workspace_id or draft.work_item_id != work_item.id:
            raise NotFoundError(f"Draft not found: {draft_id}")
        if draft.status != DraftStatus.DRAFTED:
            raise BackofficeWorkflowError("Only an active draft can be edited.")
        draft.preview_content = preview_content.strip()
        draft.updated_at = datetime.now(UTC)
        saved = self.drafts.save(draft)
        self._record_event(
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
        work_item = self._get_work_item_for_context(work_item_id, context)
        previous = self.drafts.get(draft_id)
        if previous.workspace_id != context.workspace_id or previous.work_item_id != work_item.id:
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
        self._record_event(
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
            preview_content=self._draft_preview(work_item, action_step, draft_type),
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
        approval = self._get_approval_for_context(approval_id, context)
        already_approved = approval.status == ApprovalStatus.APPROVED
        approval.approve(context.actor, notes)
        saved = self.approvals.save(approval)
        if not already_approved:
            work_item = self._get_work_item_for_context(saved.work_item_id, context)
            self._record_event(
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
        approval = self._get_approval_for_context(approval_id, context)
        already_rejected = approval.status == ApprovalStatus.REJECTED
        approval.reject(context.actor, notes)
        saved = self.approvals.save(approval)
        if not already_rejected:
            work_item = self._get_work_item_for_context(saved.work_item_id, context)
            self._record_event(
                work_item=work_item,
                event_type="approval_rejected",
                actor=context.actor,
                summary=notes or "Human approval rejected.",
            )
        return saved

    def request_correction(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        notes: str,
    ) -> WorkItem:
        work_item = self._get_work_item_for_context(work_item_id, context)
        work_item.attach_context("correction_state", "requested")
        work_item.attach_context("correction_reason", notes.strip())
        work_item.attach_context("correction_requested_by", context.actor)
        work_item.attach_context("correction_requested_at", datetime.now(UTC).isoformat())
        work_item.status = WorkItemStatus.AWAITING_HUMAN
        self.work_items.save(work_item)
        self._record_event(
            work_item=work_item,
            event_type="correction_requested",
            actor=context.actor,
            summary=notes,
        )
        return work_item

    def submit_correction(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        change_count: int,
    ) -> WorkItem:
        work_item = self._get_work_item_for_context(work_item_id, context)
        if work_item.business_context.get("correction_state") != "requested":
            return work_item
        work_item.attach_context("correction_state", "submitted")
        work_item.attach_context("correction_submitted_by", context.actor)
        work_item.attach_context("correction_change_count", str(change_count))
        work_item.status = WorkItemStatus.AWAITING_HUMAN
        saved = self.work_items.save(work_item)
        self._record_event(
            work_item=saved,
            event_type="correction_submitted",
            actor=context.actor,
            summary=f"Corrected invoice submitted with {change_count} changed fields.",
        )
        return saved

    def escalate_work_item(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        reason: str,
    ) -> WorkItem:
        work_item = self._get_work_item_for_context(work_item_id, context)
        if work_item.business_context.get("correction_state") == "requested":
            work_item.attach_context("correction_state", "escalated")
        work_item.status = WorkItemStatus.AWAITING_HUMAN
        self.work_items.save(work_item)
        self._record_event(
            work_item=work_item,
            event_type="workflow_escalated",
            actor=context.actor,
            summary=reason,
        )
        return work_item

    def execute_approved_step(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
    ) -> AgentToolResponse:
        work_item = self._get_work_item_for_context(work_item_id, context)
        plan = self._current_plan(work_item)
        step = self._find_step(plan.steps, action_step_id)
        if step.status == ActionStepStatus.EXECUTED:
            return AgentToolResponse(
                tool_name=ACTION_TOOL_MAP.get(step.action_type, AgentToolName.GET_READINESS),
                status="success",
                risk=AgentToolRisk.ADMIN_ACTION,
                summary="Action was already executed; no duplicate side effect was created.",
                confidence=AgentConfidence.HIGH,
                evidence=(f"action_step_id={step.id}", "idempotent_replay=true"),
            )
        if step.status == ActionStepStatus.BLOCKED:
            return self._blocked_response(step, step.why_not or "Action is blocked.")

        approval = self._approved_action_for_step(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            action_step_id=step.id,
        )
        if step.requires_approval and approval is None:
            return self._blocked_response(
                step,
                "Approved human confirmation is required before execution.",
                failure_type=AgentFailureType.CONFIRMATION_REQUIRED,
            )

        try:
            tool_name = ACTION_TOOL_MAP[step.action_type]
        except KeyError:
            return self._blocked_response(
                step,
                "This action is not mapped to a controlled execution tool.",
                failure_type=AgentFailureType.MISSING_TOOL,
            )
        if self.tool_executor is None:
            return self._blocked_response(
                step,
                "Controlled tool executor is not configured.",
                failure_type=AgentFailureType.MISSING_TOOL,
            )
        export_guard = self._export_execution_guard(work_item, step)
        if export_guard is not None:
            return export_guard

        started = perf_counter()
        response = self.tool_executor.execute(
            ToolExecutionRequest(
                tool_name=tool_name,
                document_id=self._selected_document_id(work_item),
                confirmed=True,
            ),
            context,
        )
        run = self._record_execution_run(
            work_item=work_item,
            plan_id=plan.id,
            response=response,
            context=context,
            latency_ms=(perf_counter() - started) * 1000,
        )
        if response.status == "success":
            step.status = ActionStepStatus.EXECUTED
            work_item.status = WorkItemStatus.RESOLVED
        else:
            step.status = ActionStepStatus.FAILED
            work_item.status = WorkItemStatus.FAILED
        self.plans.save(plan)
        self.work_items.save(work_item)
        self._record_event(
            work_item=work_item,
            event_type=("action_executed" if response.status == "success" else "action_failed"),
            actor=context.actor,
            summary=response.summary,
            agent_run_id=run.id if run else None,
        )
        return response

    def _current_plan(self, work_item: WorkItem):
        if work_item.current_plan_id is None:
            raise BackofficeWorkflowError("Work item does not have a current plan.")
        return self.plans.get(work_item.current_plan_id)

    def _find_step(self, steps: tuple[ActionStep, ...], step_id: UUID) -> ActionStep:
        for step in steps:
            if step.id == step_id:
                return step
        raise NotFoundError(f"Action step not found: {step_id}")

    def _approved_action_for_step(
        self,
        *,
        workspace_id: str,
        work_item_id: UUID,
        action_step_id: UUID,
    ) -> Approval | None:
        for approval in self.approvals.list_for_work_item(workspace_id, work_item_id):
            if (
                approval.action_step_id == action_step_id
                and approval.status == ApprovalStatus.APPROVED
            ):
                return approval
        return None

    def _get_work_item_for_context(self, work_item_id: UUID, context: SecurityContext) -> WorkItem:
        work_item = self.work_items.get(work_item_id)
        if work_item.workspace_id != context.workspace_id:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        return work_item

    def _get_approval_for_context(self, approval_id: UUID, context: SecurityContext) -> Approval:
        approval = self.approvals.get(approval_id)
        if approval.workspace_id != context.workspace_id:
            raise NotFoundError(f"Approval not found: {approval_id}")
        return approval

    def _selected_document_id(self, work_item: WorkItem) -> UUID | None:
        return work_item.linked_document_ids[0] if work_item.linked_document_ids else None

    def _export_execution_guard(
        self,
        work_item: WorkItem,
        step: ActionStep,
    ) -> AgentToolResponse | None:
        if step.action_type != ActionType.EXPORT_APPROVED_INVOICE or self.documents is None:
            return None
        document_id = self._selected_document_id(work_item)
        if document_id is None:
            return self._blocked_response(
                step,
                "Export requires a linked approved invoice.",
            )
        document = self.documents.get(document_id)
        if document.workspace_id != work_item.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        if document.status != DocumentStatus.APPROVED:
            return self._blocked_response(
                step,
                "Export requires the linked invoice to be approved first.",
            )
        return None

    def _draft_preview(
        self,
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

    def _blocked_response(
        self,
        step: ActionStep,
        summary: str,
        *,
        failure_type: AgentFailureType = AgentFailureType.INVALID_WORKFLOW_STATE,
    ) -> AgentToolResponse:
        return AgentToolResponse(
            tool_name=ACTION_TOOL_MAP.get(step.action_type, AgentToolName.GET_READINESS),
            status="blocked",
            risk=AgentToolRisk.BLOCKED,
            summary=summary,
            confidence=AgentConfidence.LOW,
            requires_follow_up=True,
            failure_type=failure_type,
            human_escalation_reason=summary,
        )

    def _record_event(
        self,
        *,
        work_item: WorkItem,
        event_type: str,
        actor: str,
        summary: str,
        agent_run_id: UUID | None = None,
    ) -> None:
        if self.workflow_events is None:
            return
        document_ids = work_item.linked_document_ids or (None,)
        for document_id in document_ids:
            self.workflow_events.add(
                WorkflowEvent(
                    workspace_id=work_item.workspace_id,
                    document_id=document_id,
                    work_item_id=work_item.id,
                    event_type=event_type,
                    actor=actor,
                    summary=summary,
                    agent_run_id=agent_run_id,
                )
            )

    def _record_plan_run(
        self, *, work_item: WorkItem, plan, context: SecurityContext, latency_ms: float
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

    def _record_execution_run(
        self,
        *,
        work_item: WorkItem,
        plan_id: UUID,
        response: AgentToolResponse,
        context: SecurityContext,
        latency_ms: float,
    ) -> AgentRun | None:
        if self.agent_runs is None:
            return None
        run = AgentRun(
            workspace_id=work_item.workspace_id,
            actor=context.actor,
            request=f"Execute controlled action for work item {work_item.id}",
            intent="backoffice_controlled_execution",
            prompt_version="deterministic-backoffice-v1",
            confidence=response.confidence,
            expected_tool=response.tool_name,
            selected_tool=response.tool_name,
            selection_reason="Mapped approved plan step to the controlled tool registry.",
            human_escalation_reason=response.human_escalation_reason,
            failure_type=response.failure_type,
            final_summary=response.summary,
            work_item_id=work_item.id,
            plan_id=plan_id,
            latency_ms=latency_ms,
        )
        run.add_tool_call(
            AgentToolCallTrace(
                tool_name=response.tool_name,
                risk=response.risk,
                status=response.status,
                summary=response.summary,
                confidence=response.confidence,
                evidence=response.evidence,
                failure_type=response.failure_type,
                human_escalation_reason=response.human_escalation_reason,
            )
        )
        return self.agent_runs.add(run)


def _normalized_key(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise BackofficeWorkflowError("Idempotency key is too long.")
    return normalized
