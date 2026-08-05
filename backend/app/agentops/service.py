from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Iterable

from app.agent.contracts import AgentConfidence, AgentFailureType
from app.agent.models import AgentRun
from app.agentops.models import (
    AgentRunEvaluation,
    FailureTrendBucket,
    MetricDelta,
    PromptVersionMetrics,
    RegressionComparison,
    ReliabilitySummary,
)


CONFIDENCE_SCORES: dict[AgentConfidence, float] = {
    AgentConfidence.HIGH: 1.0,
    AgentConfidence.MEDIUM: 0.5,
    AgentConfidence.LOW: 0.0,
}


class AgentOpsEvaluationService:
    """Read-only evaluation engine over Project 3 agent traces."""

    def evaluate_runs(self, runs: Iterable[AgentRun]) -> list[AgentRunEvaluation]:
        return [self.evaluate_run(run) for run in runs]

    def evaluate_run(self, run: AgentRun) -> AgentRunEvaluation:
        expected_tool, selected_tool = run.tool_selection_pair
        tool_selection_correct = None
        if expected_tool is not None:
            tool_selection_correct = expected_tool == selected_tool

        failure_type = run.failure_type or self._first_trace_failure(run)
        estimated_cost = run.token_usage.estimated_cost or Decimal("0")

        return AgentRunEvaluation(
            run_id=run.id,
            prompt_version=run.prompt_version,
            expected_tool=expected_tool,
            selected_tool=selected_tool,
            tool_selection_correct=tool_selection_correct,
            confidence=run.confidence,
            confidence_score=CONFIDENCE_SCORES[run.confidence],
            failure_type=failure_type,
            human_escalated=run.has_human_escalation,
            blocked_action_count=len(run.blocked_actions),
            tool_call_count=len(run.tool_calls),
            estimated_cost=estimated_cost,
            successful_completion=bool(run.final_summary) and failure_type is None,
            decision_reason=run.selection_reason,
        )

    def summarize(self, runs: Iterable[AgentRun], *, trend_limit: int = 10) -> ReliabilitySummary:
        run_list = list(runs)
        evaluations = self.evaluate_runs(run_list)
        total_runs = len(evaluations)
        evaluated = [
            evaluation
            for evaluation in evaluations
            if evaluation.tool_selection_correct is not None
        ]
        correct = [evaluation for evaluation in evaluated if evaluation.tool_selection_correct]
        blocked = [evaluation for evaluation in evaluations if evaluation.blocked_action_count > 0]
        successful = [evaluation for evaluation in evaluations if evaluation.successful_completion]
        escalated = [evaluation for evaluation in evaluations if evaluation.human_escalated]
        confidence_distribution = Counter(evaluation.confidence for evaluation in evaluations)
        failure_counts = Counter(
            evaluation.failure_type
            for evaluation in evaluations
            if evaluation.failure_type is not None
        )

        return ReliabilitySummary(
            total_runs=total_runs,
            evaluated_runs=len(evaluated),
            unevaluated_runs=total_runs - len(evaluated),
            tool_selection_accuracy=self._ratio(len(correct), len(evaluated)),
            unsafe_action_prevention_rate=self._ratio(len(blocked), len(blocked)),
            successful_completion_rate=self._ratio(len(successful), total_runs),
            escalation_rate=self._ratio(len(escalated), total_runs),
            average_confidence=self._average(
                evaluation.confidence_score for evaluation in evaluations
            ),
            average_tool_calls_per_task=self._average(
                float(evaluation.tool_call_count) for evaluation in evaluations
            ),
            average_latency_ms=self._average(
                run.latency_ms for run in run_list if run.latency_ms is not None
            ),
            estimated_cost_per_run=self._average_decimal(
                evaluation.estimated_cost for evaluation in evaluations
            ),
            confidence_distribution=dict(confidence_distribution),
            failure_counts=dict(failure_counts),
            failure_trend=self.failure_trend(run_list, limit=trend_limit),
            prompt_versions=self.prompt_version_metrics(evaluations),
        )

    def prompt_version_metrics(
        self, evaluations: Iterable[AgentRunEvaluation]
    ) -> list[PromptVersionMetrics]:
        grouped: dict[str, list[AgentRunEvaluation]] = defaultdict(list)
        for evaluation in evaluations:
            grouped[evaluation.prompt_version].append(evaluation)

        metrics: list[PromptVersionMetrics] = []
        for prompt_version, group in sorted(grouped.items()):
            evaluated = [
                evaluation for evaluation in group if evaluation.tool_selection_correct is not None
            ]
            correct = [evaluation for evaluation in evaluated if evaluation.tool_selection_correct]
            escalated = [evaluation for evaluation in group if evaluation.human_escalated]
            metrics.append(
                PromptVersionMetrics(
                    prompt_version=prompt_version,
                    total_runs=len(group),
                    evaluated_runs=len(evaluated),
                    tool_selection_accuracy=self._ratio(len(correct), len(evaluated)),
                    escalation_rate=self._ratio(len(escalated), len(group)) or 0.0,
                    average_confidence=self._average(
                        evaluation.confidence_score for evaluation in group
                    ),
                    estimated_cost_per_run=self._average_decimal(
                        evaluation.estimated_cost for evaluation in group
                    ),
                )
            )
        return metrics

    def failure_trend(
        self, runs: Iterable[AgentRun], *, limit: int = 10
    ) -> list[FailureTrendBucket]:
        recent_runs = sorted(runs, key=lambda run: run.created_at, reverse=True)[: max(limit, 0)]
        counts = Counter(
            failure for run in recent_runs for failure in self._failure_types_for_run(run)
        )
        return [
            FailureTrendBucket(failure_type=failure_type, count=count)
            for failure_type, count in sorted(
                counts.items(), key=lambda item: (item[0].value, item[1])
            )
        ]

    def compare_regression(
        self, previous: ReliabilitySummary, current: ReliabilitySummary
    ) -> RegressionComparison:
        specs = (
            ("tool_selection_accuracy", True),
            ("unsafe_action_prevention_rate", True),
            ("successful_completion_rate", True),
            ("escalation_rate", False),
            ("average_confidence", True),
        )
        deltas: list[MetricDelta] = []
        improved: list[str] = []
        regressed: list[str] = []
        for metric, higher_is_better in specs:
            previous_value = getattr(previous, metric)
            current_value = getattr(current, metric)
            delta = self._delta(previous_value, current_value)
            is_regressed = False
            if delta is not None:
                is_regressed = delta < 0 if higher_is_better else delta > 0
                is_improved = delta > 0 if higher_is_better else delta < 0
                if is_improved:
                    improved.append(metric)
                if is_regressed:
                    regressed.append(metric)
            deltas.append(
                MetricDelta(
                    metric=metric,
                    previous=previous_value,
                    current=current_value,
                    delta=delta,
                    regressed=is_regressed,
                )
            )
        return RegressionComparison(
            previous=previous,
            current=current,
            deltas=tuple(deltas),
            improved_metrics=tuple(improved),
            regressed_metrics=tuple(regressed),
        )

    def _failure_types_for_run(self, run: AgentRun) -> list[AgentFailureType]:
        failures: list[AgentFailureType] = []
        if run.failure_type is not None:
            failures.append(run.failure_type)
        failures.extend(
            trace.failure_type for trace in run.tool_calls if trace.failure_type is not None
        )
        return failures

    def _first_trace_failure(self, run: AgentRun) -> AgentFailureType | None:
        failures = self._failure_types_for_run(run)
        if failures:
            return failures[0]
        return None

    def _ratio(self, numerator: int, denominator: int) -> float | None:
        if denominator == 0:
            return None
        return numerator / denominator

    def _average(self, values: Iterable[float]) -> float | None:
        value_list = list(values)
        if not value_list:
            return None
        return sum(value_list) / len(value_list)

    def _average_decimal(self, values: Iterable[Decimal]) -> Decimal | None:
        value_list = list(values)
        if not value_list:
            return None
        return sum(value_list, Decimal("0")) / Decimal(len(value_list))

    def _delta(self, previous: float | None, current: float | None) -> float | None:
        if previous is None or current is None:
            return None
        return current - previous
