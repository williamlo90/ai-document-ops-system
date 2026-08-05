from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class WorkItem:
    workspace_id: str
    title: str
    document_id: UUID
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class PlanStep:
    title: str
    consequential: bool
    execution_authority: bool = False


@dataclass(frozen=True, slots=True)
class TaskPlan:
    work_item_id: UUID
    steps: tuple[PlanStep, ...]
    requires_approval: bool
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    plan_id: UUID
    actor: str
    approved: bool
    id: UUID = field(default_factory=uuid4)
