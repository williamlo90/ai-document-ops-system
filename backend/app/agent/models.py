from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolRisk,
)


DEFAULT_PROMPT_VERSION = "deterministic-v1"
_last_timestamp: datetime | None = None


def _monotonic_timestamp() -> datetime:
    global _last_timestamp
    current = datetime.now(UTC)
    if _last_timestamp is not None and current <= _last_timestamp:
        current = _last_timestamp + timedelta(microseconds=1)
    _last_timestamp = current
    return current


@dataclass(frozen=True)
class AgentTokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost: Decimal | None = None


@dataclass(frozen=True)
class AgentToolCallTrace:
    tool_name: AgentToolName
    risk: AgentToolRisk
    status: str
    summary: str
    confidence: AgentConfidence
    evidence: tuple[str, ...] = ()
    input_summary: str | None = None
    output_summary: str | None = None
    error_code: str | None = None
    failure_type: AgentFailureType | None = None
    retryable: bool = False
    human_escalation_reason: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_monotonic_timestamp)


@dataclass
class AgentRun:
    workspace_id: str
    actor: str
    request: str
    intent: str
    prompt_version: str = DEFAULT_PROMPT_VERSION
    confidence: AgentConfidence = AgentConfidence.MEDIUM
    expected_tool: AgentToolName | None = None
    selected_tool: AgentToolName | None = None
    selection_reason: str | None = None
    why_not: str | None = None
    human_escalation_reason: str | None = None
    failure_type: AgentFailureType | None = None
    final_summary: str | None = None
    token_usage: AgentTokenUsage = field(default_factory=AgentTokenUsage)
    work_item_id: UUID | None = None
    plan_id: UUID | None = None
    latency_ms: float | None = None
    id: UUID = field(default_factory=uuid4)
    tool_calls: list[AgentToolCallTrace] = field(default_factory=list)
    blocked_actions: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_monotonic_timestamp)
    updated_at: datetime = field(default_factory=_monotonic_timestamp)

    def add_tool_call(self, trace: AgentToolCallTrace) -> None:
        self.tool_calls.append(trace)
        self.updated_at = _monotonic_timestamp()

    def block_action(self, reason: str) -> None:
        self.blocked_actions.append(reason)
        self.updated_at = _monotonic_timestamp()

    def complete(self, summary: str) -> None:
        self.final_summary = summary
        self.updated_at = _monotonic_timestamp()

    @property
    def has_human_escalation(self) -> bool:
        if self.human_escalation_reason:
            return True
        return any(trace.human_escalation_reason for trace in self.tool_calls)

    @property
    def tool_selection_pair(self) -> tuple[AgentToolName | None, AgentToolName | None]:
        return self.expected_tool, self.selected_tool
