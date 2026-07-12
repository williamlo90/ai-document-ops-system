from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(UTC)


class WorkItemSourceType(StrEnum):
    DOCUMENT = "document"
    MANUAL = "manual"
    INTEGRATION = "integration"


class WorkType(StrEnum):
    INVOICE_REVIEW = "invoice_review"
    INVOICE_EXPORT = "invoice_export"
    ACCOUNTING_NOTE = "accounting_note"
    VENDOR_FOLLOW_UP = "vendor_follow_up"
    EXCEPTION_HANDLING = "exception_handling"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class WorkItemPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class WorkItemStatus(StrEnum):
    NEW = "new"
    CLASSIFIED = "classified"
    PLANNING = "planning"
    AWAITING_HUMAN = "awaiting_human"
    READY_TO_EXECUTE = "ready_to_execute"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    BLOCKED = "blocked"
    FAILED = "failed"


class ActionType(StrEnum):
    INSPECT_QUEUE = "inspect_queue"
    EXPLAIN_DOCUMENT = "explain_document"
    RECOMMEND_REVIEW = "recommend_review"
    DRAFT_ACCOUNTING_NOTE = "draft_accounting_note"
    DRAFT_VENDOR_MESSAGE = "draft_vendor_message"
    PROCESS_DOCUMENT = "process_document"
    EXPORT_APPROVED_INVOICE = "export_approved_invoice"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    BLOCK_UNSAFE_REQUEST = "block_unsafe_request"


class ActionRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ActionStepStatus(StrEnum):
    PLANNED = "planned"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    FAILED = "failed"


class DraftType(StrEnum):
    ACCOUNTING_NOTE = "accounting_note"
    VENDOR_MESSAGE = "vendor_message"
    EXPORT_PREVIEW = "export_preview"


class DraftStatus(StrEnum):
    DRAFTED = "drafted"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AutonomyLevel(StrEnum):
    READ_ONLY = "read_only"
    RECOMMEND = "recommend"
    DRAFT = "draft"
    CONFIRM_EXECUTE = "confirm_execute"
    BLOCKED = "blocked"


@dataclass
class WorkItem:
    workspace_id: str
    title: str
    source_type: WorkItemSourceType = WorkItemSourceType.DOCUMENT
    work_type: WorkType | None = None
    priority: WorkItemPriority = WorkItemPriority.NORMAL
    status: WorkItemStatus = WorkItemStatus.NEW
    linked_document_ids: tuple[UUID, ...] = ()
    business_context: dict[str, str] = field(default_factory=dict)
    current_plan_id: UUID | None = None
    idempotency_key: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def classify(self, work_type: WorkType, priority: WorkItemPriority | None = None) -> None:
        self.work_type = work_type
        if priority is not None:
            self.priority = priority
        self.status = WorkItemStatus.CLASSIFIED
        self.updated_at = _now()

    def link_document(self, document_id: UUID) -> None:
        if document_id not in self.linked_document_ids:
            self.linked_document_ids = (*self.linked_document_ids, document_id)
            self.updated_at = _now()

    def attach_context(self, key: str, value: str) -> None:
        self.business_context[key] = value
        self.updated_at = _now()

    def set_current_plan(self, plan_id: UUID) -> None:
        self.current_plan_id = plan_id
        self.status = WorkItemStatus.PLANNING
        self.updated_at = _now()


@dataclass
class ActionStep:
    action_type: ActionType
    risk_level: ActionRiskLevel
    tool_name: str | None = None
    requires_approval: bool = False
    status: ActionStepStatus = ActionStepStatus.PLANNED
    why_this: str | None = None
    why_not: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def mark_waiting_for_approval(self) -> None:
        self.status = ActionStepStatus.WAITING_FOR_APPROVAL
        self.updated_at = _now()

    def block(self, reason: str) -> None:
        self.status = ActionStepStatus.BLOCKED
        self.why_not = reason
        self.updated_at = _now()


@dataclass
class TaskPlan:
    workspace_id: str
    work_item_id: UUID
    planner_version: str
    steps: tuple[ActionStep, ...] = ()
    overall_confidence: str = "medium"
    escalation_reason: str | None = None
    idempotency_key: str | None = None
    agent_run_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def add_step(self, step: ActionStep) -> None:
        self.steps = (*self.steps, step)
        self.updated_at = _now()

    @property
    def requires_human(self) -> bool:
        return self.escalation_reason is not None or any(
            step.requires_approval for step in self.steps
        )


@dataclass
class ActionDraft:
    workspace_id: str
    work_item_id: UUID
    draft_type: DraftType
    preview_content: str
    action_step_id: UUID | None = None
    status: DraftStatus = DraftStatus.DRAFTED
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def approve(self) -> None:
        self.status = DraftStatus.APPROVED
        self.updated_at = _now()

    def reject(self) -> None:
        self.status = DraftStatus.REJECTED
        self.updated_at = _now()


@dataclass
class Approval:
    workspace_id: str
    work_item_id: UUID
    requested_by: str
    action_step_id: UUID | None = None
    draft_id: UUID | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewed_by: str | None = None
    reviewer_notes: str | None = None
    reviewed_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def approve(self, reviewer: str, notes: str | None = None) -> None:
        if self.status == ApprovalStatus.APPROVED:
            return
        if self.status != ApprovalStatus.PENDING:
            raise ValueError("A rejected approval cannot be approved.")
        self.status = ApprovalStatus.APPROVED
        self.reviewed_by = reviewer
        self.reviewer_notes = notes
        self.reviewed_at = _now()
        self.updated_at = _now()

    def reject(self, reviewer: str, notes: str | None = None) -> None:
        if self.status == ApprovalStatus.REJECTED:
            return
        if self.status != ApprovalStatus.PENDING:
            raise ValueError("An approved approval cannot be rejected.")
        self.status = ApprovalStatus.REJECTED
        self.reviewed_by = reviewer
        self.reviewer_notes = notes
        self.reviewed_at = _now()
        self.updated_at = _now()


@dataclass(frozen=True)
class PolicyDecision:
    workspace_id: str
    work_item_id: UUID
    action_type: ActionType
    autonomy_level: AutonomyLevel
    risk_level: ActionRiskLevel
    allowed: bool
    requires_confirmation: bool
    reason: str
    action_step_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class WorkflowEvent:
    workspace_id: str
    event_type: str
    actor: str
    summary: str
    document_id: UUID | None = None
    work_item_id: UUID | None = None
    agent_run_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_now)
