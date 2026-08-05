from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.backoffice.models import PolicyDecision, TaskPlan, WorkItem


DEFAULT_BACKOFFICE_SCENARIO_DATASET = Path(
    "examples/agentops/document_operations_scenarios_v1.json"
)
REQUIRED_BACKOFFICE_SCENARIO_FIELDS = frozenset(
    {
        "id",
        "title",
        "workspace_id",
        "actor_role",
        "document_type",
        "operation_type",
        "work_type",
        "document_state",
        "planning_input",
        "expected_plan_steps",
        "expected_step_statuses",
        "expected_risk_levels",
        "expected_policy_actions",
        "expected_requires_human",
        "expected_confidence",
        "expected_escalation_reason",
    }
)


@dataclass(frozen=True)
class BackofficeScenario:
    id: str
    title: str
    workspace_id: str
    actor_role: str
    document_type: str
    operation_type: str
    work_type: str
    document_state: str
    planning_input: dict[str, Any]
    expected_plan_steps: tuple[str, ...]
    expected_step_statuses: tuple[str, ...]
    expected_risk_levels: tuple[str, ...]
    expected_policy_actions: tuple[str, ...]
    expected_requires_human: bool
    expected_confidence: str
    expected_escalation_reason: str | None


@dataclass(frozen=True)
class BackofficeScenarioDataset:
    dataset_id: str
    dataset_version: str
    created_at: str
    description: str
    scenarios: tuple[BackofficeScenario, ...]


@dataclass(frozen=True)
class BackofficeScenarioEvaluationResult:
    dataset_id: str
    dataset_version: str
    scenario_id: str
    work_item_id: str
    plan_id: str
    passed: bool
    checks: dict[str, bool]
    expected_plan_steps: tuple[str, ...]
    actual_plan_steps: tuple[str, ...]
    expected_policy_actions: tuple[str, ...]
    actual_policy_actions: tuple[str, ...]
    expected_requires_human: bool
    actual_requires_human: bool
    expected_confidence: str
    actual_confidence: str
    expected_document_type: str
    actual_document_type: str
    expected_operation_type: str
    actual_operation_type: str


def load_backoffice_scenario_dataset(
    path: Path = DEFAULT_BACKOFFICE_SCENARIO_DATASET,
) -> BackofficeScenarioDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    scenarios = tuple(_scenario_from_mapping(item) for item in raw.get("scenarios", ()))
    if not scenarios:
        raise ValueError("Backoffice scenario dataset must include at least one scenario.")
    return BackofficeScenarioDataset(
        dataset_id=_required_text(raw, "dataset_id"),
        dataset_version=_required_text(raw, "dataset_version"),
        created_at=_required_text(raw, "created_at"),
        description=_required_text(raw, "description"),
        scenarios=scenarios,
    )


def get_backoffice_scenario(
    dataset: BackofficeScenarioDataset, scenario_id: str
) -> BackofficeScenario:
    for scenario in dataset.scenarios:
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"Unknown backoffice scenario: {scenario_id}")


def evaluate_backoffice_scenario_plan(
    *,
    dataset: BackofficeScenarioDataset,
    scenario: BackofficeScenario,
    work_item: WorkItem,
    plan: TaskPlan,
    policy_decisions: list[PolicyDecision],
) -> BackofficeScenarioEvaluationResult:
    actual_steps = tuple(step.action_type.value for step in plan.steps)
    actual_statuses = tuple(step.status.value for step in plan.steps)
    actual_risks = tuple(step.risk_level.value for step in plan.steps)
    actual_policy_actions = tuple(decision.action_type.value for decision in policy_decisions)
    actual_document_type = "invoice"
    actual_operation_type = _operation_type_for_work_type(
        work_item.work_type.value if work_item.work_type is not None else None
    )
    checks = {
        "workspace": work_item.workspace_id == scenario.workspace_id,
        "document_type": actual_document_type == scenario.document_type,
        "operation_type": actual_operation_type == scenario.operation_type,
        "work_type": (
            work_item.work_type is not None and work_item.work_type.value == scenario.work_type
        ),
        "plan_steps": actual_steps == scenario.expected_plan_steps,
        "step_statuses": actual_statuses == scenario.expected_step_statuses,
        "risk_levels": actual_risks == scenario.expected_risk_levels,
        "policy_actions": _contains_in_order(
            actual_policy_actions, scenario.expected_policy_actions
        ),
        "requires_human": plan.requires_human == scenario.expected_requires_human,
        "confidence": plan.overall_confidence == scenario.expected_confidence,
        "escalation_reason": (plan.escalation_reason == scenario.expected_escalation_reason),
    }
    return BackofficeScenarioEvaluationResult(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        scenario_id=scenario.id,
        work_item_id=str(work_item.id),
        plan_id=str(plan.id),
        passed=all(checks.values()),
        checks=checks,
        expected_plan_steps=scenario.expected_plan_steps,
        actual_plan_steps=actual_steps,
        expected_policy_actions=scenario.expected_policy_actions,
        actual_policy_actions=actual_policy_actions,
        expected_requires_human=scenario.expected_requires_human,
        actual_requires_human=plan.requires_human,
        expected_confidence=scenario.expected_confidence,
        actual_confidence=plan.overall_confidence,
        expected_document_type=scenario.document_type,
        actual_document_type=actual_document_type,
        expected_operation_type=scenario.operation_type,
        actual_operation_type=actual_operation_type,
    )


def _scenario_from_mapping(raw: dict[str, Any]) -> BackofficeScenario:
    missing = REQUIRED_BACKOFFICE_SCENARIO_FIELDS.difference(raw)
    if missing:
        raise ValueError(f"Backoffice scenario is missing required fields: {sorted(missing)}")
    return BackofficeScenario(
        id=_required_text(raw, "id"),
        title=_required_text(raw, "title"),
        workspace_id=_required_text(raw, "workspace_id"),
        actor_role=_required_text(raw, "actor_role"),
        document_type=_required_text(raw, "document_type"),
        operation_type=_required_text(raw, "operation_type"),
        work_type=_required_text(raw, "work_type"),
        document_state=_required_text(raw, "document_state"),
        planning_input=_required_mapping(raw, "planning_input"),
        expected_plan_steps=_required_text_tuple(raw, "expected_plan_steps"),
        expected_step_statuses=_required_text_tuple(raw, "expected_step_statuses"),
        expected_risk_levels=_required_text_tuple(raw, "expected_risk_levels"),
        expected_policy_actions=_required_text_tuple(raw, "expected_policy_actions"),
        expected_requires_human=bool(raw["expected_requires_human"]),
        expected_confidence=_required_text(raw, "expected_confidence"),
        expected_escalation_reason=raw.get("expected_escalation_reason"),
    )


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _required_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object.")
    return dict(value)


def _required_text_tuple(raw: dict[str, Any], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty list.")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{key} must contain only non-empty strings.")
    return tuple(value)


def _contains_in_order(actual: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    if len(actual) < len(expected):
        return False
    start = 0
    for item in expected:
        try:
            index = actual.index(item, start)
        except ValueError:
            return False
        start = index + 1
    return True


def _operation_type_for_work_type(work_type: str | None) -> str:
    return {
        "invoice_review": "document_review",
        "invoice_export": "document_export",
        "vendor_follow_up": "document_follow_up",
        "accounting_note": "document_note",
        "insufficient_evidence": "document_escalation",
    }.get(work_type or "", "document_operation")
