from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json
from typing import Protocol
from uuid import UUID

from app.agent.contracts import AgentConfidence, AgentFailureType, AgentToolName, AgentToolRisk
from app.agent.models import AgentRun, AgentTokenUsage, AgentToolCallTrace
from app.documents.repositories import NotFoundError


class AgentRunRepository(Protocol):
    def add(self, run: AgentRun) -> AgentRun: ...

    def get(self, run_id: UUID) -> AgentRun: ...

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[AgentRun]: ...


@dataclass
class InMemoryAgentRunRepository:
    records: dict[UUID, AgentRun] = field(default_factory=dict)

    def add(self, run: AgentRun) -> AgentRun:
        self.records[run.id] = run
        return run

    def get(self, run_id: UUID) -> AgentRun:
        try:
            return self.records[run_id]
        except KeyError as exc:
            raise NotFoundError(f"Agent run not found: {run_id}") from exc

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[AgentRun]:
        matching = [run for run in self.records.values() if run.workspace_id == workspace_id]
        matching.sort(key=lambda run: run.created_at, reverse=True)
        return matching[: max(limit, 0)]


class SqliteAgentRunRepository:
    def __init__(self, store) -> None:
        self.store = store

    def add(self, run: AgentRun) -> AgentRun:
        self.store.execute(
            """
            INSERT OR REPLACE INTO agent_runs (id, workspace_id, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(run.id),
                run.workspace_id,
                run.created_at.isoformat(),
                json.dumps(_run_to_dict(run)),
            ),
        )
        return run

    def get(self, run_id: UUID) -> AgentRun:
        row = self.store.query_one("SELECT payload FROM agent_runs WHERE id = ?", (str(run_id),))
        if row is None:
            raise NotFoundError(f"Agent run not found: {run_id}")
        return _run_from_dict(json.loads(row["payload"]))

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[AgentRun]:
        rows = self.store.query(
            """
            SELECT payload FROM agent_runs
            WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (workspace_id, max(limit, 0)),
        )
        return [_run_from_dict(json.loads(row["payload"])) for row in rows]


def _run_to_dict(run: AgentRun) -> dict[str, object]:
    return {
        "id": str(run.id),
        "workspace_id": run.workspace_id,
        "actor": run.actor,
        "request": run.request,
        "intent": run.intent,
        "prompt_version": run.prompt_version,
        "confidence": run.confidence.value,
        "expected_tool": run.expected_tool.value if run.expected_tool else None,
        "selected_tool": run.selected_tool.value if run.selected_tool else None,
        "selection_reason": run.selection_reason,
        "why_not": run.why_not,
        "human_escalation_reason": run.human_escalation_reason,
        "failure_type": run.failure_type.value if run.failure_type else None,
        "final_summary": run.final_summary,
        "token_usage": {
            "prompt_tokens": run.token_usage.prompt_tokens,
            "completion_tokens": run.token_usage.completion_tokens,
            "estimated_cost": (
                str(run.token_usage.estimated_cost)
                if run.token_usage.estimated_cost is not None
                else None
            ),
        },
        "work_item_id": str(run.work_item_id) if run.work_item_id else None,
        "plan_id": str(run.plan_id) if run.plan_id else None,
        "latency_ms": run.latency_ms,
        "tool_calls": [_trace_to_dict(trace) for trace in run.tool_calls],
        "blocked_actions": list(run.blocked_actions),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _run_from_dict(value: dict[str, object]) -> AgentRun:
    usage = value.get("token_usage") or {}
    assert isinstance(usage, dict)
    cost = usage.get("estimated_cost")
    run = AgentRun(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        actor=str(value["actor"]),
        request=str(value["request"]),
        intent=str(value["intent"]),
        prompt_version=str(value["prompt_version"]),
        confidence=AgentConfidence(str(value["confidence"])),
        expected_tool=(
            AgentToolName(str(value["expected_tool"])) if value.get("expected_tool") else None
        ),
        selected_tool=(
            AgentToolName(str(value["selected_tool"])) if value.get("selected_tool") else None
        ),
        selection_reason=str(value["selection_reason"]) if value.get("selection_reason") else None,
        why_not=str(value["why_not"]) if value.get("why_not") else None,
        human_escalation_reason=(
            str(value["human_escalation_reason"]) if value.get("human_escalation_reason") else None
        ),
        failure_type=(
            AgentFailureType(str(value["failure_type"])) if value.get("failure_type") else None
        ),
        final_summary=str(value["final_summary"]) if value.get("final_summary") else None,
        token_usage=AgentTokenUsage(
            prompt_tokens=(
                int(usage["prompt_tokens"]) if usage.get("prompt_tokens") is not None else None
            ),
            completion_tokens=(
                int(usage["completion_tokens"])
                if usage.get("completion_tokens") is not None
                else None
            ),
            estimated_cost=Decimal(str(cost)) if cost is not None else None,
        ),
        work_item_id=UUID(str(value["work_item_id"])) if value.get("work_item_id") else None,
        plan_id=UUID(str(value["plan_id"])) if value.get("plan_id") else None,
        latency_ms=float(value["latency_ms"]) if value.get("latency_ms") is not None else None,
        tool_calls=[_trace_from_dict(item) for item in value.get("tool_calls", [])],
        blocked_actions=[str(item) for item in value.get("blocked_actions", [])],
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )
    return run


def _trace_to_dict(trace: AgentToolCallTrace) -> dict[str, object]:
    return {
        "id": str(trace.id),
        "tool_name": trace.tool_name.value,
        "risk": trace.risk.value,
        "status": trace.status,
        "summary": trace.summary,
        "confidence": trace.confidence.value,
        "evidence": list(trace.evidence),
        "input_summary": trace.input_summary,
        "output_summary": trace.output_summary,
        "error_code": trace.error_code,
        "failure_type": trace.failure_type.value if trace.failure_type else None,
        "retryable": trace.retryable,
        "human_escalation_reason": trace.human_escalation_reason,
        "created_at": trace.created_at.isoformat(),
    }


def _trace_from_dict(value: dict[str, object]) -> AgentToolCallTrace:
    return AgentToolCallTrace(
        id=UUID(str(value["id"])),
        tool_name=AgentToolName(str(value["tool_name"])),
        risk=AgentToolRisk(str(value["risk"])),
        status=str(value["status"]),
        summary=str(value["summary"]),
        confidence=AgentConfidence(str(value["confidence"])),
        evidence=tuple(str(item) for item in value.get("evidence", [])),
        input_summary=str(value["input_summary"]) if value.get("input_summary") else None,
        output_summary=str(value["output_summary"]) if value.get("output_summary") else None,
        error_code=str(value["error_code"]) if value.get("error_code") else None,
        failure_type=(
            AgentFailureType(str(value["failure_type"])) if value.get("failure_type") else None
        ),
        retryable=bool(value.get("retryable", False)),
        human_escalation_reason=(
            str(value["human_escalation_reason"]) if value.get("human_escalation_reason") else None
        ),
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )
