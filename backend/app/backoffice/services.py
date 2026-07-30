from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.agent.contracts import AgentToolResponse
from app.agent.models import AgentRun
from app.agent.repositories import AgentRunRepository
from app.backoffice.errors import BackofficeWorkflowError as BackofficeWorkflowError
from app.backoffice.execution import (
    BackofficeExecutionCoordinator,
    BackofficeExecutionReservation,
    BackofficeToolExecutor,
)
from app.backoffice.models import (
    ActionDraft,
    ActionStep,
    Approval,
    DraftType,
    TaskPlan,
    WorkflowEvent,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkType,
)
from app.backoffice.planning_service import (
    BackofficePlanningService,
    BackofficePlanResult,
)
from app.backoffice.planner import BackofficePlanner, PlanningInput
from app.backoffice.policy import AutonomyPolicyEngine
from app.backoffice.recovery import BackofficeExecutionRecovery
from app.backoffice.repositories import (
    ActionDraftRepository,
    ApprovalRepository,
    PolicyDecisionRepository,
    TaskPlanRepository,
    WorkItemRepository,
    WorkflowEventRepository,
)
from app.backoffice.request_identity import (
    normalized_key as _normalized_key,
    require_matching_fingerprint as _require_matching_fingerprint,
    work_item_fingerprint as _work_item_fingerprint,
)
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.repositories import DocumentRepository, NotFoundError


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
        transactions: TransactionManager,
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
        self.transactions = transactions
        self._planning = BackofficePlanningService(
            work_items=work_items,
            plans=plans,
            drafts=drafts,
            approvals=approvals,
            policy_decisions=policy_decisions,
            transactions=transactions,
            record_event=self._record_event,
            planner=self.planner,
            policy=self.policy,
            agent_runs=agent_runs,
        )
        self._execution = BackofficeExecutionCoordinator(
            work_items=work_items,
            plans=plans,
            approvals=approvals,
            transactions=transactions,
            record_event=self._record_event,
            tool_executor=tool_executor,
            agent_runs=agent_runs,
            documents=documents,
        )
        self._recovery = BackofficeExecutionRecovery(
            work_items=work_items,
            plans=plans,
            transactions=transactions,
            record_event=self._record_event,
        )

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
        fingerprint = _work_item_fingerprint(
            title=title,
            work_type=work_type,
            linked_document_ids=linked_document_ids,
            business_context=business_context or {},
        )
        with self.transactions.transaction():
            if normalized_key:
                existing = self.work_items.get_by_idempotency_key(
                    context.workspace_id,
                    normalized_key,
                )
                if existing is not None:
                    _require_matching_fingerprint(
                        existing.idempotency_fingerprint,
                        fingerprint,
                    )
                    return existing
            work_item = WorkItem(
                workspace_id=context.workspace_id,
                title=title,
                work_type=work_type,
                linked_document_ids=linked_document_ids,
                business_context=dict(business_context or {}),
                idempotency_key=normalized_key,
                idempotency_fingerprint=fingerprint if normalized_key else None,
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
        return self._planning.plan_work_item(
            work_item_id=work_item_id,
            context=context,
            planning_input=planning_input,
            idempotency_key=idempotency_key,
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
        with self.transactions.transaction():
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
        return self._planning.edit_draft(
            work_item_id=work_item_id,
            draft_id=draft_id,
            context=context,
            preview_content=preview_content,
        )

    def regenerate_draft(
        self,
        *,
        work_item_id: UUID,
        draft_id: UUID,
        context: SecurityContext,
    ) -> ActionDraft:
        return self._planning.regenerate_draft(
            work_item_id=work_item_id,
            draft_id=draft_id,
            context=context,
        )

    def create_draft_for_step(
        self,
        *,
        work_item_id: UUID,
        action_step: ActionStep,
        context: SecurityContext,
    ) -> ActionDraft:
        return self._planning.create_draft_for_step(
            work_item_id=work_item_id,
            action_step=action_step,
            context=context,
        )

    def request_approval_for_step(
        self,
        *,
        work_item_id: UUID,
        action_step: ActionStep,
        context: SecurityContext,
    ) -> Approval:
        return self._planning.request_approval_for_step(
            work_item_id=work_item_id,
            action_step=action_step,
            context=context,
        )

    def approve_request(
        self,
        *,
        approval_id: UUID,
        context: SecurityContext,
        notes: str | None = None,
    ) -> Approval:
        return self._planning.approve_request(
            approval_id=approval_id,
            context=context,
            notes=notes,
        )

    def reject_request(
        self,
        *,
        approval_id: UUID,
        context: SecurityContext,
        notes: str | None = None,
    ) -> Approval:
        return self._planning.reject_request(
            approval_id=approval_id,
            context=context,
            notes=notes,
        )

    def request_correction(
        self,
        *,
        work_item_id: UUID,
        context: SecurityContext,
        notes: str,
    ) -> WorkItem:
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            work_item.attach_context("correction_state", "requested")
            work_item.attach_context("correction_reason", notes.strip())
            work_item.attach_context("correction_requested_by", context.actor)
            work_item.attach_context(
                "correction_requested_at",
                datetime.now(UTC).isoformat(),
            )
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
        with self.transactions.transaction():
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
        with self.transactions.transaction():
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
        return self._execution.execute_approved_step(
            work_item_id=work_item_id,
            action_step_id=action_step_id,
            context=context,
        )

    def _reserve_approved_execution(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
    ) -> BackofficeExecutionReservation | AgentToolResponse:
        return self._execution.reserve_approved_execution(
            work_item_id=work_item_id,
            action_step_id=action_step_id,
            context=context,
        )

    def _renew_execution_reservation(
        self,
        reservation: BackofficeExecutionReservation,
        context: SecurityContext,
    ) -> bool:
        return self._execution.renew_execution_reservation(reservation, context)

    def _mark_execution_outcome_unknown(
        self,
        reservation: BackofficeExecutionReservation,
        context: SecurityContext,
    ) -> AgentToolResponse:
        return self._execution.mark_execution_outcome_unknown(reservation, context)

    def _finalize_reserved_execution(
        self,
        reservation: BackofficeExecutionReservation,
        response: AgentToolResponse,
        context: SecurityContext,
        started: float,
    ) -> AgentToolResponse:
        return self._execution.finalize_reserved_execution(
            reservation,
            response,
            context,
            started,
        )

    def reconcile_execution(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
        succeeded: bool,
        summary: str,
    ) -> WorkItem:
        return self._recovery.reconcile_execution(
            work_item_id=work_item_id,
            action_step_id=action_step_id,
            context=context,
            succeeded=succeeded,
            summary=summary,
        )

    def _plan_result_for(
        self,
        work_item: WorkItem,
        plan: TaskPlan,
        workspace_id: str,
    ) -> BackofficePlanResult:
        return self._planning.plan_result_for(work_item, plan, workspace_id)

    def _plan_containing_step(self, work_item: WorkItem, step_id: UUID) -> TaskPlan:
        return self._recovery.plan_containing_step(work_item, step_id)

    def _require_no_pending_execution(self, work_item: WorkItem) -> None:
        self._planning.require_no_pending_execution(work_item)

    def _reservation_matches(
        self,
        work_item: WorkItem,
        reservation: BackofficeExecutionReservation,
    ) -> bool:
        return self._execution.reservation_matches(work_item, reservation)

    def _execution_target_matches(
        self,
        work_item: WorkItem,
        plan_id: UUID,
        step_id: UUID,
    ) -> bool:
        return self._execution.execution_target_matches(work_item, plan_id, step_id)

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

    def _draft_preview(
        self,
        work_item: WorkItem,
        action_step: ActionStep,
        draft_type: DraftType,
    ) -> str:
        return self._planning.draft_preview(work_item, action_step, draft_type)

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
        self,
        *,
        work_item: WorkItem,
        plan: TaskPlan,
        context: SecurityContext,
        latency_ms: float,
    ) -> AgentRun | None:
        return self._planning.record_plan_run(
            work_item=work_item,
            plan=plan,
            context=context,
            latency_ms=latency_ms,
        )
