from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.agent.contracts import AgentConfidence, AgentFailureType, AgentToolName


@dataclass(frozen=True)
class AgentRunEvaluation:
    run_id: UUID
    prompt_version: str
    expected_tool: AgentToolName | None
    selected_tool: AgentToolName | None
    tool_selection_correct: bool | None
    confidence: AgentConfidence
    confidence_score: float
    failure_type: AgentFailureType | None
    human_escalated: bool
    blocked_action_count: int
    tool_call_count: int
    estimated_cost: Decimal
    successful_completion: bool
    decision_reason: str | None


@dataclass(frozen=True)
class PromptVersionMetrics:
    prompt_version: str
    total_runs: int
    evaluated_runs: int
    tool_selection_accuracy: float | None
    escalation_rate: float
    average_confidence: float | None
    estimated_cost_per_run: Decimal | None


@dataclass(frozen=True)
class FailureTrendBucket:
    failure_type: AgentFailureType
    count: int


@dataclass(frozen=True)
class ReliabilitySummary:
    total_runs: int
    evaluated_runs: int
    unevaluated_runs: int
    tool_selection_accuracy: float | None
    unsafe_action_prevention_rate: float | None
    successful_completion_rate: float | None
    escalation_rate: float | None
    average_confidence: float | None
    average_tool_calls_per_task: float | None
    average_latency_ms: float | None
    estimated_cost_per_run: Decimal | None
    confidence_distribution: dict[AgentConfidence, int] = field(default_factory=dict)
    failure_counts: dict[AgentFailureType, int] = field(default_factory=dict)
    failure_trend: list[FailureTrendBucket] = field(default_factory=list)
    prompt_versions: list[PromptVersionMetrics] = field(default_factory=list)


@dataclass(frozen=True)
class MetricDelta:
    metric: str
    previous: float | None
    current: float | None
    delta: float | None
    regressed: bool


@dataclass(frozen=True)
class RegressionComparison:
    previous: ReliabilitySummary
    current: ReliabilitySummary
    deltas: tuple[MetricDelta, ...]
    improved_metrics: tuple[str, ...]
    regressed_metrics: tuple[str, ...]
