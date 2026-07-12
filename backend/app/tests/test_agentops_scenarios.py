from __future__ import annotations

import unittest

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolRisk,
)
from app.agent.models import AgentRun, AgentToolCallTrace
from app.agentops.scenarios import (
    DEFAULT_SCENARIO_DATASET,
    evaluate_scenario_run,
    get_scenario,
    load_scenario_dataset,
)


def _run_for_tool(
    *,
    intent: str,
    selected_tool: AgentToolName,
    risk: AgentToolRisk,
    selection_reason: str,
    failure_type: AgentFailureType | None = None,
    human_escalation_reason: str | None = None,
) -> AgentRun:
    run = AgentRun(
        workspace_id="default",
        actor="admin",
        request="scenario",
        intent=intent,
        expected_tool=selected_tool,
        selected_tool=selected_tool,
        selection_reason=selection_reason,
        failure_type=failure_type,
        human_escalation_reason=human_escalation_reason,
    )
    run.add_tool_call(
        AgentToolCallTrace(
            tool_name=selected_tool,
            risk=risk,
            status="success" if failure_type is None else "escalated",
            summary="scenario trace",
            confidence=AgentConfidence.HIGH if failure_type is None else AgentConfidence.LOW,
            failure_type=failure_type,
            human_escalation_reason=human_escalation_reason,
        )
    )
    run.complete("scenario complete")
    return run


class AgentOpsScenarioTests(unittest.TestCase):
    def test_loads_versioned_dataset(self) -> None:
        dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)

        self.assertEqual(dataset.dataset_id, "agentops_core")
        self.assertEqual(dataset.dataset_version, "v1")
        self.assertEqual(len(dataset.scenarios), 9)
        self.assertEqual(dataset.scenarios[0].id, "workflow_summary")

    def test_evaluates_matched_scenario_run(self) -> None:
        dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
        scenario = get_scenario(dataset, "workflow_summary")
        run = _run_for_tool(
            intent="summarize_workflow",
            selected_tool=AgentToolName.GET_METRICS_SUMMARY,
            risk=AgentToolRisk.READ_ONLY,
            selection_reason="Selected get_metrics_summary from deterministic routing.",
        )

        result = evaluate_scenario_run(dataset=dataset, scenario=scenario, run=run)

        self.assertTrue(result.passed)
        self.assertTrue(all(result.checks.values()))
        self.assertEqual(result.expected_tool, "get_metrics_summary")
        self.assertEqual(result.selected_tool, "get_metrics_summary")

    def test_evaluates_tool_mismatch(self) -> None:
        dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
        scenario = get_scenario(dataset, "workflow_summary")
        run = _run_for_tool(
            intent="summarize_workflow",
            selected_tool=AgentToolName.LIST_DOCUMENTS,
            risk=AgentToolRisk.READ_ONLY,
            selection_reason="Selected list_documents from deterministic routing.",
        )

        result = evaluate_scenario_run(dataset=dataset, scenario=scenario, run=run)

        self.assertFalse(result.passed)
        self.assertFalse(result.checks["tool"])

    def test_evaluates_blocked_action_scenario(self) -> None:
        dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
        scenario = get_scenario(dataset, "unsafe_direct_database_edit")
        run = AgentRun(
            workspace_id="default",
            actor="admin",
            request=scenario.message,
            intent="blocked_request",
            selection_reason=None,
            failure_type=AgentFailureType.PERMISSION_DENIED,
            human_escalation_reason="Unsafe direct mutation requires human review.",
        )
        run.block_action("Direct database mutation is blocked.")
        run.complete("Blocked unsafe request.")

        result = evaluate_scenario_run(dataset=dataset, scenario=scenario, run=run)

        self.assertTrue(result.passed)
        self.assertTrue(result.checks["tool"])
        self.assertTrue(result.checks["risk"])
        self.assertEqual(result.actual_outcome, "blocked")

    def test_evaluates_human_escalation_scenario(self) -> None:
        dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
        scenario = get_scenario(dataset, "insufficient_evidence")
        run = _run_for_tool(
            intent="explain_document",
            selected_tool=AgentToolName.GET_DOCUMENT_DETAIL,
            risk=AgentToolRisk.READ_ONLY,
            selection_reason="Selected get_document_detail from deterministic routing.",
            failure_type=AgentFailureType.INSUFFICIENT_EVIDENCE,
            human_escalation_reason="A reviewer should inspect this unclear invoice.",
        )

        result = evaluate_scenario_run(dataset=dataset, scenario=scenario, run=run)

        self.assertTrue(result.passed)
        self.assertEqual(result.actual_outcome, "human_escalation")
        self.assertEqual(result.actual_failure_type, "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
