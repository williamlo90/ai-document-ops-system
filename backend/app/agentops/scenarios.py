from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.contracts import AgentFailureType
from app.agent.models import AgentRun
from app.agentops.service import AgentOpsEvaluationService


DEFAULT_SCENARIO_DATASET = Path("examples/agentops/scenarios_v1.json")
REQUIRED_SCENARIO_FIELDS = frozenset(
    {
        "id",
        "message",
        "document_state",
        "actor_role",
        "workspace_id",
        "expected_intent",
        "expected_tool",
        "expected_risk",
        "expected_outcome",
        "expected_failure_type",
        "should_escalate_to_human",
        "prompt_version",
        "decision_reason_expected",
    }
)


@dataclass(frozen=True)
class AgentOpsScenario:
    id: str
    message: str
    document_state: str
    actor_role: str
    workspace_id: str
    expected_intent: str
    expected_tool: str
    expected_risk: str
    expected_outcome: str
    expected_failure_type: str | None
    should_escalate_to_human: bool
    prompt_version: str
    decision_reason_expected: str | None = None


@dataclass(frozen=True)
class AgentOpsScenarioDataset:
    dataset_id: str
    dataset_version: str
    created_at: str
    description: str
    scenarios: tuple[AgentOpsScenario, ...]


@dataclass(frozen=True)
class ScenarioEvaluationResult:
    dataset_id: str
    dataset_version: str
    scenario_id: str
    run_id: str
    passed: bool
    checks: dict[str, bool]
    expected_tool: str
    selected_tool: str | None
    expected_outcome: str
    actual_outcome: str
    expected_failure_type: str | None
    actual_failure_type: str | None


def load_scenario_dataset(path: Path = DEFAULT_SCENARIO_DATASET) -> AgentOpsScenarioDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = tuple(_scenario_from_mapping(item) for item in raw.get("scenarios", ()))
    if not scenarios:
        raise ValueError("Scenario dataset must include at least one scenario.")
    return AgentOpsScenarioDataset(
        dataset_id=_required_text(raw, "dataset_id"),
        dataset_version=_required_text(raw, "dataset_version"),
        created_at=_required_text(raw, "created_at"),
        description=_required_text(raw, "description"),
        scenarios=scenarios,
    )


def get_scenario(dataset: AgentOpsScenarioDataset, scenario_id: str) -> AgentOpsScenario:
    for scenario in dataset.scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario: {scenario_id}")


def evaluate_scenario_run(
    *,
    dataset: AgentOpsScenarioDataset,
    scenario: AgentOpsScenario,
    run: AgentRun,
    evaluator: AgentOpsEvaluationService | None = None,
) -> ScenarioEvaluationResult:
    service = evaluator or AgentOpsEvaluationService()
    evaluation = service.evaluate_run(run)
    selected_tool = evaluation.selected_tool.value if evaluation.selected_tool else None
    actual_failure_type = (
        evaluation.failure_type.value if evaluation.failure_type is not None else None
    )
    checks = {
        "workspace": run.workspace_id == scenario.workspace_id,
        "intent": run.intent == scenario.expected_intent,
        "tool": _tool_matches(
            scenario.expected_tool, selected_tool, evaluation.blocked_action_count
        ),
        "risk": _risk_matches(run, scenario.expected_risk),
        "outcome": _outcome_matches(scenario.expected_outcome, run, actual_failure_type),
        "failure_type": scenario.expected_failure_type == actual_failure_type,
        "human_escalation": (scenario.should_escalate_to_human == evaluation.human_escalated),
        "prompt_version": run.prompt_version == scenario.prompt_version,
        "decision_reason": _decision_reason_matches(
            scenario.decision_reason_expected, evaluation.decision_reason, run.blocked_actions
        ),
    }
    return ScenarioEvaluationResult(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        scenario_id=scenario.id,
        run_id=str(run.id),
        passed=all(checks.values()),
        checks=checks,
        expected_tool=scenario.expected_tool,
        selected_tool=selected_tool,
        expected_outcome=scenario.expected_outcome,
        actual_outcome=_actual_outcome(run, actual_failure_type),
        expected_failure_type=scenario.expected_failure_type,
        actual_failure_type=actual_failure_type,
    )


def _scenario_from_mapping(raw: dict[str, Any]) -> AgentOpsScenario:
    missing = REQUIRED_SCENARIO_FIELDS.difference(raw)
    if missing:
        raise ValueError(f"Scenario is missing required fields: {sorted(missing)}")
    return AgentOpsScenario(
        id=_required_text(raw, "id"),
        message=_required_text(raw, "message"),
        document_state=_required_text(raw, "document_state"),
        actor_role=_required_text(raw, "actor_role"),
        workspace_id=_required_text(raw, "workspace_id"),
        expected_intent=_required_text(raw, "expected_intent"),
        expected_tool=_required_text(raw, "expected_tool"),
        expected_risk=_required_text(raw, "expected_risk"),
        expected_outcome=_required_text(raw, "expected_outcome"),
        expected_failure_type=raw.get("expected_failure_type"),
        should_escalate_to_human=bool(raw["should_escalate_to_human"]),
        prompt_version=_required_text(raw, "prompt_version"),
        decision_reason_expected=raw.get("decision_reason_expected"),
    )


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _tool_matches(expected_tool: str, selected_tool: str | None, blocked_action_count: int) -> bool:
    if expected_tool == "blocked_action":
        return blocked_action_count > 0
    return selected_tool == expected_tool


def _risk_matches(run: AgentRun, expected_risk: str) -> bool:
    if expected_risk == "blocked":
        return bool(run.blocked_actions)
    return any(trace.risk.value == expected_risk for trace in run.tool_calls)


def _outcome_matches(expected_outcome: str, run: AgentRun, actual_failure_type: str | None) -> bool:
    actual = _actual_outcome(run, actual_failure_type)
    if expected_outcome == "confirmation_required_or_success":
        return actual in {"confirmation_required", "success"}
    return actual == expected_outcome


def _actual_outcome(run: AgentRun, actual_failure_type: str | None) -> str:
    if run.blocked_actions:
        return "blocked"
    if run.has_human_escalation:
        if actual_failure_type == AgentFailureType.CONFIRMATION_REQUIRED.value:
            return "confirmation_required"
        return "human_escalation"
    if actual_failure_type is not None:
        return "safe_failure"
    return "success"


def _decision_reason_matches(
    expected: str | None, actual: str | None, blocked_actions: list[str]
) -> bool:
    if not expected:
        return True
    if expected == "blocked":
        return bool(blocked_actions)
    return actual is not None and expected in actual
