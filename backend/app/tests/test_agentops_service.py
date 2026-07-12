from __future__ import annotations

import unittest
from decimal import Decimal

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolRisk,
)
from app.agent.models import AgentRun, AgentTokenUsage, AgentToolCallTrace
from app.agentops.service import AgentOpsEvaluationService


def _run(
    *,
    request: str = "What needs review?",
    prompt_version: str = "deterministic-v1",
    confidence: AgentConfidence = AgentConfidence.HIGH,
    expected_tool: AgentToolName | None = AgentToolName.LIST_REVIEW_QUEUE,
    selected_tool: AgentToolName | None = AgentToolName.LIST_REVIEW_QUEUE,
    selection_reason: str | None = "The request asks for documents needing review.",
    failure_type: AgentFailureType | None = None,
    final_summary: str | None = "Done",
    estimated_cost: Decimal = Decimal("0.010"),
) -> AgentRun:
    return AgentRun(
        workspace_id="default",
        actor="admin",
        request=request,
        intent="test",
        prompt_version=prompt_version,
        confidence=confidence,
        expected_tool=expected_tool,
        selected_tool=selected_tool,
        selection_reason=selection_reason,
        failure_type=failure_type,
        final_summary=final_summary,
        token_usage=AgentTokenUsage(estimated_cost=estimated_cost),
    )


class AgentOpsEvaluationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentOpsEvaluationService()

    def test_evaluates_single_run_without_mutating_trace(self) -> None:
        run = _run()
        before_tool_calls = list(run.tool_calls)

        evaluation = self.service.evaluate_run(run)

        self.assertEqual(evaluation.expected_tool, AgentToolName.LIST_REVIEW_QUEUE)
        self.assertEqual(evaluation.selected_tool, AgentToolName.LIST_REVIEW_QUEUE)
        self.assertTrue(evaluation.tool_selection_correct)
        self.assertEqual(evaluation.confidence_score, 1.0)
        self.assertTrue(evaluation.successful_completion)
        self.assertEqual(
            evaluation.decision_reason,
            "The request asks for documents needing review.",
        )
        self.assertEqual(run.tool_calls, before_tool_calls)

    def test_summary_tracks_accuracy_unevaluated_confidence_cost_and_completion(self) -> None:
        matched = _run(estimated_cost=Decimal("0.010"))
        mismatched = _run(
            selected_tool=AgentToolName.GET_METRICS_SUMMARY,
            confidence=AgentConfidence.MEDIUM,
            estimated_cost=Decimal("0.020"),
        )
        unevaluated = _run(
            expected_tool=None,
            selected_tool=AgentToolName.GET_READINESS,
            confidence=AgentConfidence.LOW,
            final_summary=None,
            estimated_cost=Decimal("0"),
        )

        summary = self.service.summarize([matched, mismatched, unevaluated])

        self.assertEqual(summary.total_runs, 3)
        self.assertEqual(summary.evaluated_runs, 2)
        self.assertEqual(summary.unevaluated_runs, 1)
        self.assertEqual(summary.tool_selection_accuracy, 0.5)
        self.assertEqual(summary.successful_completion_rate, 2 / 3)
        self.assertEqual(summary.average_confidence, 0.5)
        self.assertEqual(summary.average_tool_calls_per_task, 0.0)
        self.assertEqual(summary.estimated_cost_per_run, Decimal("0.010"))
        self.assertEqual(summary.confidence_distribution[AgentConfidence.HIGH], 1)
        self.assertEqual(summary.confidence_distribution[AgentConfidence.MEDIUM], 1)
        self.assertEqual(summary.confidence_distribution[AgentConfidence.LOW], 1)

    def test_blocked_and_failure_runs_feed_prevention_failure_and_escalation_metrics(self) -> None:
        blocked = _run(
            confidence=AgentConfidence.LOW,
            failure_type=AgentFailureType.PERMISSION_DENIED,
            final_summary=None,
        )
        blocked.block_action("Direct database mutation is blocked.")
        blocked.human_escalation_reason = "Human approval required."
        blocked.add_tool_call(
            AgentToolCallTrace(
                tool_name=AgentToolName.EXPORT_APPROVED_CSV,
                risk=AgentToolRisk.ADMIN_ACTION,
                status="failed",
                summary="Confirmation required",
                confidence=AgentConfidence.LOW,
                failure_type=AgentFailureType.CONFIRMATION_REQUIRED,
            )
        )

        summary = self.service.summarize([blocked])

        self.assertEqual(summary.unsafe_action_prevention_rate, 1.0)
        self.assertEqual(summary.successful_completion_rate, 0.0)
        self.assertEqual(summary.escalation_rate, 1.0)
        self.assertEqual(summary.failure_counts[AgentFailureType.PERMISSION_DENIED], 1)
        self.assertEqual(
            summary.failure_trend[0].failure_type,
            AgentFailureType.CONFIRMATION_REQUIRED,
        )
        self.assertEqual(summary.failure_trend[1].failure_type, AgentFailureType.PERMISSION_DENIED)

    def test_prompt_version_metrics_compare_accuracy_escalation_confidence_and_cost(self) -> None:
        v1_good = _run(prompt_version="v1", estimated_cost=Decimal("0.010"))
        v1_bad = _run(
            prompt_version="v1",
            selected_tool=AgentToolName.GET_METRICS_SUMMARY,
            confidence=AgentConfidence.MEDIUM,
            estimated_cost=Decimal("0.030"),
        )
        v2_low = _run(
            prompt_version="v2",
            confidence=AgentConfidence.LOW,
            estimated_cost=Decimal("0.020"),
        )
        v2_low.human_escalation_reason = "Needs reviewer."

        summary = self.service.summarize([v1_good, v1_bad, v2_low])
        by_prompt = {item.prompt_version: item for item in summary.prompt_versions}

        self.assertEqual(by_prompt["v1"].tool_selection_accuracy, 0.5)
        self.assertEqual(by_prompt["v1"].average_confidence, 0.75)
        self.assertEqual(by_prompt["v1"].estimated_cost_per_run, Decimal("0.020"))
        self.assertEqual(by_prompt["v2"].tool_selection_accuracy, 1.0)
        self.assertEqual(by_prompt["v2"].escalation_rate, 1.0)
        self.assertEqual(by_prompt["v2"].average_confidence, 0.0)

    def test_regression_comparison_flags_worse_metrics(self) -> None:
        previous = self.service.summarize([_run(), _run()])
        current = self.service.summarize(
            [
                _run(selected_tool=AgentToolName.GET_METRICS_SUMMARY),
                _run(selected_tool=AgentToolName.GET_METRICS_SUMMARY),
            ]
        )

        comparison = self.service.compare_regression(previous, current)

        self.assertIn("tool_selection_accuracy", comparison.regressed_metrics)
        accuracy_delta = next(
            delta for delta in comparison.deltas if delta.metric == "tool_selection_accuracy"
        )
        self.assertEqual(accuracy_delta.previous, 1.0)
        self.assertEqual(accuracy_delta.current, 0.0)
        self.assertEqual(accuracy_delta.delta, -1.0)
        self.assertTrue(accuracy_delta.regressed)

    def test_empty_summary_is_honest_about_missing_evidence(self) -> None:
        summary = self.service.summarize([])

        self.assertEqual(summary.total_runs, 0)
        self.assertIsNone(summary.tool_selection_accuracy)
        self.assertIsNone(summary.unsafe_action_prevention_rate)
        self.assertIsNone(summary.successful_completion_rate)
        self.assertIsNone(summary.average_confidence)
        self.assertIsNone(summary.estimated_cost_per_run)


if __name__ == "__main__":
    unittest.main()
