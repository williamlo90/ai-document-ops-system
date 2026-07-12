from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from typing import Protocol
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ScenarioEvaluationRecord:
    workspace_id: str
    evaluation_type: str
    dataset_id: str
    dataset_version: str
    scenario_id: str
    target_id: str
    passed: bool
    evidence: dict[str, object]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ScenarioEvaluationRepository(Protocol):
    def add(self, record: ScenarioEvaluationRecord) -> ScenarioEvaluationRecord: ...
    def list_recent(
        self, workspace_id: str, limit: int = 100
    ) -> list[ScenarioEvaluationRecord]: ...


@dataclass
class InMemoryScenarioEvaluationRepository:
    records: list[ScenarioEvaluationRecord] = field(default_factory=list)

    def add(self, record: ScenarioEvaluationRecord) -> ScenarioEvaluationRecord:
        self.records.append(record)
        return record

    def list_recent(self, workspace_id: str, limit: int = 100) -> list[ScenarioEvaluationRecord]:
        records = [record for record in self.records if record.workspace_id == workspace_id]
        return sorted(records, key=lambda record: record.created_at, reverse=True)[: max(limit, 0)]


class SqliteScenarioEvaluationRepository:
    def __init__(self, store) -> None:
        self.store = store

    def add(self, record: ScenarioEvaluationRecord) -> ScenarioEvaluationRecord:
        self.store.execute(
            """
            INSERT INTO agentops_evaluations
            (id, workspace_id, evaluation_type, scenario_id, created_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(record.id),
                record.workspace_id,
                record.evaluation_type,
                record.scenario_id,
                record.created_at.isoformat(),
                json.dumps(_record_response(record)),
            ),
        )
        return record

    def list_recent(self, workspace_id: str, limit: int = 100) -> list[ScenarioEvaluationRecord]:
        rows = self.store.query(
            """
            SELECT payload FROM agentops_evaluations
            WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (workspace_id, max(limit, 0)),
        )
        return [_record_from_dict(json.loads(row["payload"])) for row in rows]


def record_response(record: ScenarioEvaluationRecord) -> dict[str, object]:
    return _record_response(record)


def _record_response(record: ScenarioEvaluationRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "workspace_id": record.workspace_id,
        "evaluation_type": record.evaluation_type,
        "dataset_id": record.dataset_id,
        "dataset_version": record.dataset_version,
        "scenario_id": record.scenario_id,
        "target_id": record.target_id,
        "passed": record.passed,
        "evidence": record.evidence,
        "created_at": record.created_at.isoformat(),
    }


def _record_from_dict(value: dict[str, object]) -> ScenarioEvaluationRecord:
    evidence = value.get("evidence")
    return ScenarioEvaluationRecord(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        evaluation_type=str(value["evaluation_type"]),
        dataset_id=str(value["dataset_id"]),
        dataset_version=str(value["dataset_version"]),
        scenario_id=str(value["scenario_id"]),
        target_id=str(value["target_id"]),
        passed=bool(value["passed"]),
        evidence=dict(evidence) if isinstance(evidence, dict) else {},
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )
