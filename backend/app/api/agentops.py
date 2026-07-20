from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.agentops.models import (
    AgentRunEvaluation,
    MetricDelta,
    PromptVersionMetrics,
    RegressionComparison,
    ReliabilitySummary,
)
from app.agentops.backoffice_scenarios import (
    DEFAULT_BACKOFFICE_SCENARIO_DATASET,
    evaluate_backoffice_scenario_plan,
    get_backoffice_scenario,
    load_backoffice_scenario_dataset,
)
from app.agentops.scenarios import (
    DEFAULT_SCENARIO_DATASET,
    evaluate_scenario_run,
    get_scenario,
    load_scenario_dataset,
)
from app.agentops.repositories import ScenarioEvaluationRecord, record_response
from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext
from app.documents.repositories import NotFoundError
from app.evaluation.report_summary import load_latest_provider_cost_summary


router = APIRouter(prefix="/agentops", tags=["agentops"])


class ScenarioEvaluationPayload(BaseModel):
    scenario_id: str
    run_id: UUID


class BackofficeScenarioEvaluationPayload(BaseModel):
    scenario_id: str
    work_item_id: UUID


@router.get("/runs")
def list_agent_runs(
    limit: int = 20,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    runs = container.agent_runs.list_recent(context.workspace_id, limit=limit)
    evaluations = {
        evaluation.run_id: evaluation
        for evaluation in container.agentops_service.evaluate_runs(runs)
    }
    return {
        "runs": [
            _run_response(run, evaluations[run.id])
            for run in runs
            if run.workspace_id == context.workspace_id
        ]
    }


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: UUID,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    try:
        run = container.agent_runs.get(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if run.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    evaluation = container.agentops_service.evaluate_run(run)
    return _run_response(run, evaluation, include_tool_calls=True)


@router.get("/summary")
def reliability_summary(
    limit: int = 100,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    runs = container.agent_runs.list_recent(context.workspace_id, limit=limit)
    summary = container.agentops_service.summarize(runs)
    return {"summary": _summary_response(summary)}


@router.get("/provider-costs")
def provider_cost_summary(
    _context: SecurityContext = Depends(require_admin_context),
) -> dict[str, object]:
    return {"provider_costs": load_latest_provider_cost_summary()}


@router.get("/prompt-versions")
def prompt_version_comparison(
    limit: int = 100,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    runs = container.agent_runs.list_recent(context.workspace_id, limit=limit)
    evaluations = container.agentops_service.evaluate_runs(runs)
    return {
        "prompt_versions": [
            _prompt_version_response(metrics)
            for metrics in container.agentops_service.prompt_version_metrics(evaluations)
        ]
    }


@router.post("/regression")
def regression_comparison(
    payload: dict[str, int],
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    previous_limit = max(int(payload.get("previous_limit", 20)), 0)
    current_limit = max(int(payload.get("current_limit", 20)), 0)
    runs = container.agent_runs.list_recent(
        context.workspace_id, limit=previous_limit + current_limit
    )
    current_runs = runs[:current_limit]
    previous_runs = runs[current_limit : current_limit + previous_limit]
    comparison = container.agentops_service.compare_regression(
        container.agentops_service.summarize(previous_runs),
        container.agentops_service.summarize(current_runs),
    )
    return {"regression": _regression_response(comparison)}


@router.get("/scenarios")
def scenario_contract(
    _context: SecurityContext = Depends(require_admin_context),
) -> dict[str, object]:
    dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "created_at": dataset.created_at,
        "description": dataset.description,
        "scenario_count": len(dataset.scenarios),
        "scenarios": [_scenario_response(scenario) for scenario in dataset.scenarios],
        "required_fields": [
            "id",
            "dataset_id",
            "dataset_version",
            "message",
            "expected_tool",
            "expected_risk",
            "expected_outcome",
            "prompt_version",
        ],
    }


@router.post("/scenarios/evaluate")
def evaluate_scenario(
    payload: ScenarioEvaluationPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    dataset = load_scenario_dataset(DEFAULT_SCENARIO_DATASET)
    try:
        scenario = get_scenario(dataset, payload.scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    try:
        run = container.agent_runs.get(payload.run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if run.workspace_id != context.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    result = evaluate_scenario_run(
        dataset=dataset,
        scenario=scenario,
        run=run,
        evaluator=container.agentops_service,
    )
    evidence = _scenario_evaluation_response(result)
    container.scenario_evaluations.add(
        ScenarioEvaluationRecord(
            workspace_id=context.workspace_id,
            evaluation_type="agent",
            dataset_id=result.dataset_id,
            dataset_version=result.dataset_version,
            scenario_id=result.scenario_id,
            target_id=result.run_id,
            passed=result.passed,
            evidence=evidence,
        )
    )
    return {"result": evidence}


@router.get("/backoffice/scenarios")
def backoffice_scenario_contract(
    _context: SecurityContext = Depends(require_admin_context),
) -> dict[str, object]:
    dataset = load_backoffice_scenario_dataset(DEFAULT_BACKOFFICE_SCENARIO_DATASET)
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "created_at": dataset.created_at,
        "description": dataset.description,
        "scenario_count": len(dataset.scenarios),
        "scenarios": [_backoffice_scenario_response(scenario) for scenario in dataset.scenarios],
        "required_fields": [
            "id",
            "dataset_id",
            "dataset_version",
            "document_type",
            "operation_type",
            "work_type",
            "planning_input",
            "expected_plan_steps",
            "expected_policy_actions",
            "expected_requires_human",
        ],
    }


@router.post("/backoffice/scenarios/evaluate")
def evaluate_backoffice_scenario(
    payload: BackofficeScenarioEvaluationPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    dataset = load_backoffice_scenario_dataset(DEFAULT_BACKOFFICE_SCENARIO_DATASET)
    try:
        scenario = get_backoffice_scenario(dataset, payload.scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    try:
        work_item = container.backoffice_work_items.get(payload.work_item_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc
    if work_item.workspace_id != context.workspace_id or work_item.current_plan_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    plan = container.backoffice_plans.get(work_item.current_plan_id)
    policy_decisions = container.backoffice_policy_decisions.list_for_work_item(
        context.workspace_id, work_item.id
    )
    result = evaluate_backoffice_scenario_plan(
        dataset=dataset,
        scenario=scenario,
        work_item=work_item,
        plan=plan,
        policy_decisions=policy_decisions,
    )
    evidence = _backoffice_scenario_evaluation_response(result)
    container.scenario_evaluations.add(
        ScenarioEvaluationRecord(
            workspace_id=context.workspace_id,
            evaluation_type="backoffice",
            dataset_id=result.dataset_id,
            dataset_version=result.dataset_version,
            scenario_id=result.scenario_id,
            target_id=result.work_item_id,
            passed=result.passed,
            evidence=evidence,
        )
    )
    return {"result": evidence}


@router.get("/evaluations")
def list_scenario_evaluations(
    limit: int = 100,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    return {
        "evaluations": [
            record_response(record)
            for record in container.scenario_evaluations.list_recent(
                context.workspace_id, limit=limit
            )
        ]
    }


def _run_response(run, evaluation: AgentRunEvaluation, *, include_tool_calls: bool = False):
    payload: dict[str, object] = {
        "id": str(run.id),
        "workspace_id": run.workspace_id,
        "actor": run.actor,
        "request": run.request,
        "intent": run.intent,
        "prompt_version": run.prompt_version,
        "work_item_id": str(run.work_item_id) if run.work_item_id else None,
        "plan_id": str(run.plan_id) if run.plan_id else None,
        "latency_ms": run.latency_ms,
        "token_usage": {
            "prompt_tokens": run.token_usage.prompt_tokens,
            "completion_tokens": run.token_usage.completion_tokens,
            "estimated_cost_usd": _decimal(run.token_usage.estimated_cost),
        },
        "created_at": run.created_at.isoformat(),
        "evaluation": _evaluation_response(evaluation),
    }
    if include_tool_calls:
        payload["tool_calls"] = [
            {
                "id": str(trace.id),
                "tool_name": trace.tool_name.value,
                "risk": trace.risk.value,
                "status": trace.status,
                "summary": trace.summary,
                "confidence": trace.confidence.value,
                "failure_type": trace.failure_type.value if trace.failure_type else None,
                "human_escalation_reason": trace.human_escalation_reason,
            }
            for trace in run.tool_calls
        ]
        payload["blocked_actions"] = list(run.blocked_actions)
        payload["final_summary"] = run.final_summary
    return payload


def _evaluation_response(evaluation: AgentRunEvaluation) -> dict[str, object]:
    return {
        "expected_tool": (evaluation.expected_tool.value if evaluation.expected_tool else None),
        "selected_tool": (evaluation.selected_tool.value if evaluation.selected_tool else None),
        "tool_selection_correct": evaluation.tool_selection_correct,
        "confidence": evaluation.confidence.value,
        "confidence_score": evaluation.confidence_score,
        "failure_type": (evaluation.failure_type.value if evaluation.failure_type else None),
        "human_escalated": evaluation.human_escalated,
        "blocked_action_count": evaluation.blocked_action_count,
        "tool_call_count": evaluation.tool_call_count,
        "estimated_cost_usd": _decimal(evaluation.estimated_cost),
        "successful_completion": evaluation.successful_completion,
        "decision_reason": evaluation.decision_reason,
    }


def _summary_response(summary: ReliabilitySummary) -> dict[str, object]:
    return {
        "total_runs": summary.total_runs,
        "evaluated_runs": summary.evaluated_runs,
        "unevaluated_runs": summary.unevaluated_runs,
        "tool_selection_accuracy": summary.tool_selection_accuracy,
        "unsafe_action_prevention_rate": summary.unsafe_action_prevention_rate,
        "successful_completion_rate": summary.successful_completion_rate,
        "escalation_rate": summary.escalation_rate,
        "average_confidence": summary.average_confidence,
        "average_tool_calls_per_task": summary.average_tool_calls_per_task,
        "average_latency_ms": summary.average_latency_ms,
        "estimated_cost_per_run": _decimal(summary.estimated_cost_per_run),
        "confidence_distribution": {
            confidence.value: count for confidence, count in summary.confidence_distribution.items()
        },
        "failure_counts": {
            failure_type.value: count for failure_type, count in summary.failure_counts.items()
        },
        "failure_trend": [
            {"failure_type": bucket.failure_type.value, "count": bucket.count}
            for bucket in summary.failure_trend
        ],
        "prompt_versions": [
            _prompt_version_response(metrics) for metrics in summary.prompt_versions
        ],
    }


def _prompt_version_response(metrics: PromptVersionMetrics) -> dict[str, object]:
    return {
        "prompt_version": metrics.prompt_version,
        "total_runs": metrics.total_runs,
        "evaluated_runs": metrics.evaluated_runs,
        "tool_selection_accuracy": metrics.tool_selection_accuracy,
        "escalation_rate": metrics.escalation_rate,
        "average_confidence": metrics.average_confidence,
        "estimated_cost_per_run": _decimal(metrics.estimated_cost_per_run),
    }


def _regression_response(comparison: RegressionComparison) -> dict[str, object]:
    return {
        "previous": _summary_response(comparison.previous),
        "current": _summary_response(comparison.current),
        "deltas": [_metric_delta_response(delta) for delta in comparison.deltas],
        "improved_metrics": list(comparison.improved_metrics),
        "regressed_metrics": list(comparison.regressed_metrics),
    }


def _metric_delta_response(delta: MetricDelta) -> dict[str, object]:
    return {
        "metric": delta.metric,
        "previous": delta.previous,
        "current": delta.current,
        "delta": delta.delta,
        "regressed": delta.regressed,
    }


def _decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _scenario_response(scenario) -> dict[str, object]:
    return {
        "id": scenario.id,
        "message": scenario.message,
        "document_state": scenario.document_state,
        "actor_role": scenario.actor_role,
        "workspace_id": scenario.workspace_id,
        "expected_intent": scenario.expected_intent,
        "expected_tool": scenario.expected_tool,
        "expected_risk": scenario.expected_risk,
        "expected_outcome": scenario.expected_outcome,
        "expected_failure_type": scenario.expected_failure_type,
        "should_escalate_to_human": scenario.should_escalate_to_human,
        "prompt_version": scenario.prompt_version,
        "decision_reason_expected": scenario.decision_reason_expected,
    }


def _scenario_evaluation_response(result) -> dict[str, object]:
    return {
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "scenario_id": result.scenario_id,
        "run_id": result.run_id,
        "passed": result.passed,
        "checks": result.checks,
        "expected_tool": result.expected_tool,
        "selected_tool": result.selected_tool,
        "expected_outcome": result.expected_outcome,
        "actual_outcome": result.actual_outcome,
        "expected_failure_type": result.expected_failure_type,
        "actual_failure_type": result.actual_failure_type,
    }


def _backoffice_scenario_response(scenario) -> dict[str, object]:
    return {
        "id": scenario.id,
        "title": scenario.title,
        "workspace_id": scenario.workspace_id,
        "actor_role": scenario.actor_role,
        "document_type": scenario.document_type,
        "operation_type": scenario.operation_type,
        "work_type": scenario.work_type,
        "document_state": scenario.document_state,
        "planning_input": scenario.planning_input,
        "expected_plan_steps": list(scenario.expected_plan_steps),
        "expected_step_statuses": list(scenario.expected_step_statuses),
        "expected_risk_levels": list(scenario.expected_risk_levels),
        "expected_policy_actions": list(scenario.expected_policy_actions),
        "expected_requires_human": scenario.expected_requires_human,
        "expected_confidence": scenario.expected_confidence,
        "expected_escalation_reason": scenario.expected_escalation_reason,
    }


def _backoffice_scenario_evaluation_response(result) -> dict[str, object]:
    return {
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "scenario_id": result.scenario_id,
        "work_item_id": result.work_item_id,
        "plan_id": result.plan_id,
        "passed": result.passed,
        "checks": result.checks,
        "expected_plan_steps": list(result.expected_plan_steps),
        "actual_plan_steps": list(result.actual_plan_steps),
        "expected_policy_actions": list(result.expected_policy_actions),
        "actual_policy_actions": list(result.actual_policy_actions),
        "expected_requires_human": result.expected_requires_human,
        "actual_requires_human": result.actual_requires_human,
        "expected_confidence": result.expected_confidence,
        "actual_confidence": result.actual_confidence,
        "expected_document_type": result.expected_document_type,
        "actual_document_type": result.actual_document_type,
        "expected_operation_type": result.expected_operation_type,
        "actual_operation_type": result.actual_operation_type,
    }
