from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event, Thread
from time import perf_counter
from typing import Protocol
from uuid import UUID, uuid4

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
from app.backoffice.errors import BackofficeWorkflowError
from app.backoffice.models import (
    ActionStep,
    ActionStepStatus,
    ActionType,
    Approval,
    ApprovalStatus,
    TaskPlan,
    WorkItem,
    WorkItemStatus,
)
from app.backoffice.repositories import (
    ApprovalRepository,
    TaskPlanRepository,
    WorkItemRepository,
)
from app.core.security import SecurityContext
from app.core.transactions import TransactionManager
from app.documents.repositories import DocumentRepository, NotFoundError
from app.documents.status import DocumentStatus


class BackofficeToolExecutor(Protocol):
    def execute(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse: ...


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
class BackofficeExecutionReservation:
    work_item: WorkItem
    plan_id: UUID
    step: ActionStep
    tool_name: AgentToolName
    executor: BackofficeToolExecutor
    execution_token: str


EXECUTION_LEASE_SECONDS = 300


class ExecutionHeartbeat:
    def __init__(self, renew: Callable[[], bool]) -> None:
        self.renew = renew
        self.interval_seconds = min(30.0, EXECUTION_LEASE_SECONDS / 3)
        self._stopping = Event()
        self._thread = Thread(target=self._run, name="backoffice-execution-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._thread.join(timeout=self.interval_seconds + 1)

    def _run(self) -> None:
        while not self._stopping.wait(self.interval_seconds):
            try:
                if not self.renew():
                    return
            except Exception:
                continue


ACTION_TOOL_MAP: dict[ActionType, AgentToolName] = {
    ActionType.PROCESS_DOCUMENT: AgentToolName.PROCESS_DOCUMENT,
    ActionType.EXPORT_APPROVED_INVOICE: AgentToolName.EXPORT_APPROVED_CSV,
}


class BackofficeExecutionCoordinator:
    def __init__(
        self,
        *,
        work_items: WorkItemRepository,
        plans: TaskPlanRepository,
        approvals: ApprovalRepository,
        transactions: TransactionManager,
        record_event: WorkflowEventRecorder,
        tool_executor: BackofficeToolExecutor | None,
        agent_runs: AgentRunRepository | None,
        documents: DocumentRepository | None,
    ) -> None:
        self.work_items = work_items
        self.plans = plans
        self.approvals = approvals
        self.transactions = transactions
        self.record_event = record_event
        self.tool_executor = tool_executor
        self.agent_runs = agent_runs
        self.documents = documents

    def execute_approved_step(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
    ) -> AgentToolResponse:
        reservation = self.reserve_approved_execution(
            work_item_id=work_item_id,
            action_step_id=action_step_id,
            context=context,
        )
        if isinstance(reservation, AgentToolResponse):
            return reservation

        started = perf_counter()
        heartbeat = ExecutionHeartbeat(
            lambda: self.renew_execution_reservation(reservation, context)
        )
        heartbeat.start()
        try:
            response = reservation.executor.execute(
                ToolExecutionRequest(
                    tool_name=reservation.tool_name,
                    document_id=self._selected_document_id(reservation.work_item),
                    confirmed=True,
                ),
                context,
            )
        except Exception:
            return self.mark_execution_outcome_unknown(reservation, context)
        finally:
            heartbeat.stop()

        try:
            return self.finalize_reserved_execution(
                reservation,
                response,
                context,
                started,
            )
        except Exception:
            try:
                self.mark_execution_outcome_unknown(reservation, context)
            except Exception:
                # Preserve the finalization failure; an unmarked reservation remains blocked.
                pass
            raise

    def reserve_approved_execution(
        self,
        *,
        work_item_id: UUID,
        action_step_id: UUID,
        context: SecurityContext,
    ) -> BackofficeExecutionReservation | AgentToolResponse:
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(work_item_id, context)
            plan = self._current_plan(work_item)
            step = self._find_step(plan.steps, action_step_id)
            execution = self._execution_tool_or_error(work_item, step)
            if isinstance(execution, AgentToolResponse):
                return execution

            tool_name, executor = execution
            execution_token = uuid4().hex
            now = datetime.now(UTC)
            step.status = ActionStepStatus.EXECUTING
            step.updated_at = now
            work_item.status = WorkItemStatus.EXECUTING
            work_item.attach_context("execution_token", execution_token)
            work_item.attach_context("execution_outcome", "in_flight")
            work_item.attach_context("execution_heartbeat_at", now.isoformat())
            work_item.attach_context("execution_plan_id", str(plan.id))
            work_item.attach_context("execution_step_id", str(step.id))
            work_item.updated_at = now
            self.plans.save(plan)
            self.work_items.save(work_item)
            self.record_event(
                work_item=work_item,
                event_type="action_execution_started",
                actor=context.actor,
                summary=f"Controlled execution reserved for {step.action_type.value}.",
            )
            return BackofficeExecutionReservation(
                work_item=work_item,
                plan_id=plan.id,
                step=step,
                tool_name=tool_name,
                executor=executor,
                execution_token=execution_token,
            )

    def renew_execution_reservation(
        self,
        reservation: BackofficeExecutionReservation,
        context: SecurityContext,
    ) -> bool:
        with self.transactions.transaction():
            work_item = self._get_work_item_for_context(reservation.work_item.id, context)
            plan = self.plans.get(reservation.plan_id)
            step = self._find_step(plan.steps, reservation.step.id)
            if (
                step.status != ActionStepStatus.EXECUTING
                or work_item.business_context.get("execution_outcome") != "in_flight"
                or not self.reservation_matches(work_item, reservation)
            ):
                return False
            work_item.attach_context(
                "execution_heartbeat_at",
                datetime.now(UTC).isoformat(),
            )
            self.work_items.save(work_item)
            return True

    def mark_execution_outcome_unknown(
        self,
        reservation: BackofficeExecutionReservation,
        context: SecurityContext,
    ) -> AgentToolResponse:
        with self.transactions.transaction():
            current_item = self._get_work_item_for_context(reservation.work_item.id, context)
            current_plan = self.plans.get(reservation.plan_id)
            current_step = self._find_step(current_plan.steps, reservation.step.id)
            if current_step.status == ActionStepStatus.EXECUTING and self.reservation_matches(
                current_item, reservation
            ):
                current_item.status = WorkItemStatus.AWAITING_HUMAN
                current_item.attach_context("execution_outcome", "unknown")
                self.work_items.save(current_item)
                self.record_event(
                    work_item=current_item,
                    event_type="action_execution_outcome_unknown",
                    actor=context.actor,
                    summary=(
                        "The tool call did not return a confirmed outcome; "
                        "manual reconciliation is required."
                    ),
                )
        return self.blocked_response(
            reservation.step,
            "The execution outcome is unknown and must be reconciled before retrying.",
            failure_type=AgentFailureType.TOOL_EXECUTION_FAILED,
        )

    def finalize_reserved_execution(
        self,
        reservation: BackofficeExecutionReservation,
        response: AgentToolResponse,
        context: SecurityContext,
        started: float,
    ) -> AgentToolResponse:
        with self.transactions.transaction():
            current_item = self._get_work_item_for_context(reservation.work_item.id, context)
            current_plan = self.plans.get(reservation.plan_id)
            current_step = self._find_step(current_plan.steps, reservation.step.id)
            if current_step.status != ActionStepStatus.EXECUTING or not self.reservation_matches(
                current_item, reservation
            ):
                return self.blocked_response(
                    current_step,
                    "The execution reservation is no longer active.",
                    failure_type=AgentFailureType.INVALID_WORKFLOW_STATE,
                )
            run = self._record_execution_run(
                work_item=current_item,
                plan_id=current_plan.id,
                response=response,
                context=context,
                latency_ms=(perf_counter() - started) * 1000,
            )
            if response.status == "success":
                current_step.status = ActionStepStatus.EXECUTED
                current_item.status = WorkItemStatus.RESOLVED
                current_item.attach_context("execution_outcome", "confirmed_success")
            else:
                current_step.status = ActionStepStatus.FAILED
                current_item.status = WorkItemStatus.FAILED
                current_item.attach_context("execution_outcome", "confirmed_failure")
            current_step.updated_at = datetime.now(UTC)
            current_item.updated_at = current_step.updated_at
            self.plans.save(current_plan)
            self.work_items.save(current_item)
            self.record_event(
                work_item=current_item,
                event_type=("action_executed" if response.status == "success" else "action_failed"),
                actor=context.actor,
                summary=response.summary,
                agent_run_id=run.id if run else None,
            )
        return response

    def reservation_matches(
        self,
        work_item: WorkItem,
        reservation: BackofficeExecutionReservation,
    ) -> bool:
        return work_item.business_context.get(
            "execution_token"
        ) == reservation.execution_token and self.execution_target_matches(
            work_item,
            reservation.plan_id,
            reservation.step.id,
        )

    @staticmethod
    def execution_target_matches(
        work_item: WorkItem,
        plan_id: UUID,
        step_id: UUID,
    ) -> bool:
        return work_item.business_context.get("execution_plan_id") == str(
            plan_id
        ) and work_item.business_context.get("execution_step_id") == str(step_id)

    def _execution_tool_or_error(
        self,
        work_item: WorkItem,
        step: ActionStep,
    ) -> tuple[AgentToolName, BackofficeToolExecutor] | AgentToolResponse:
        if step.status == ActionStepStatus.EXECUTED:
            return AgentToolResponse(
                tool_name=ACTION_TOOL_MAP.get(
                    step.action_type,
                    AgentToolName.GET_READINESS,
                ),
                status="success",
                risk=AgentToolRisk.ADMIN_ACTION,
                summary="Action was already executed; no duplicate side effect was created.",
                confidence=AgentConfidence.HIGH,
                evidence=(f"action_step_id={step.id}", "idempotent_replay=true"),
            )
        if step.status == ActionStepStatus.EXECUTING:
            return self.blocked_response(
                step,
                "The previous execution outcome must be reconciled before another attempt.",
                failure_type=AgentFailureType.TOOL_EXECUTION_FAILED,
            )
        if step.status in {ActionStepStatus.BLOCKED, ActionStepStatus.FAILED}:
            return self.blocked_response(step, step.why_not or "Action is blocked.")
        approval = self._approved_action_for_step(
            workspace_id=work_item.workspace_id,
            work_item_id=work_item.id,
            action_step_id=step.id,
        )
        if step.requires_approval and approval is None:
            return self.blocked_response(
                step,
                "Approved human confirmation is required before execution.",
                failure_type=AgentFailureType.CONFIRMATION_REQUIRED,
            )
        tool_name = ACTION_TOOL_MAP.get(step.action_type)
        if tool_name is None:
            return self.blocked_response(
                step,
                "This action is not mapped to a controlled execution tool.",
                failure_type=AgentFailureType.MISSING_TOOL,
            )
        if self.tool_executor is None:
            return self.blocked_response(
                step,
                "Controlled tool executor is not configured.",
                failure_type=AgentFailureType.MISSING_TOOL,
            )
        export_guard = self._export_execution_guard(work_item, step)
        if export_guard is not None:
            return export_guard
        return tool_name, self.tool_executor

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

    @staticmethod
    def _find_step(steps: tuple[ActionStep, ...], step_id: UUID) -> ActionStep:
        for step in steps:
            if step.id == step_id:
                return step
        raise NotFoundError(f"Action step not found: {step_id}")

    def _get_work_item_for_context(
        self,
        work_item_id: UUID,
        context: SecurityContext,
    ) -> WorkItem:
        work_item = self.work_items.get(work_item_id)
        if work_item.workspace_id != context.workspace_id:
            raise NotFoundError(f"Work item not found: {work_item_id}")
        return work_item

    def _current_plan(self, work_item: WorkItem) -> TaskPlan:
        if work_item.current_plan_id is None:
            raise BackofficeWorkflowError("Work item does not have a current plan.")
        return self.plans.get(work_item.current_plan_id)

    @staticmethod
    def _selected_document_id(work_item: WorkItem) -> UUID | None:
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
            return self.blocked_response(
                step,
                "Export requires a linked approved invoice.",
            )
        document = self.documents.get(document_id)
        if document.workspace_id != work_item.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        if document.status != DocumentStatus.APPROVED:
            return self.blocked_response(
                step,
                "Export requires the linked invoice to be approved first.",
            )
        return None

    @staticmethod
    def blocked_response(
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
