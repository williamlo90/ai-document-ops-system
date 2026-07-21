from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid4

from app.documents.sqlite_repositories import SqliteStore


class EvaluationAttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class EvaluationAttemptRecord:
    workspace_id: str
    requested_by: str
    dataset_id: str
    dataset_version: str
    documents_requested: int
    id: UUID = field(default_factory=uuid4)
    status: EvaluationAttemptStatus = EvaluationAttemptStatus.RUNNING
    documents_processed: int = 0
    provider_calls: int = 0
    run_id: UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def succeeded(
        self, *, run_id: UUID, documents_processed: int, provider_calls: int
    ) -> "EvaluationAttemptRecord":
        now = datetime.now(UTC)
        return replace(
            self,
            status=EvaluationAttemptStatus.SUCCEEDED,
            documents_processed=documents_processed,
            provider_calls=provider_calls,
            run_id=run_id,
            completed_at=now,
            updated_at=now,
        )

    def failed(self, *, documents_processed: int, provider_calls: int) -> "EvaluationAttemptRecord":
        now = datetime.now(UTC)
        return replace(
            self,
            status=EvaluationAttemptStatus.FAILED,
            documents_processed=documents_processed,
            provider_calls=provider_calls,
            error_code="evaluation_incomplete",
            error_message="The provider-backed evaluation did not complete. No partial result was promoted.",
            completed_at=now,
            updated_at=now,
        )


class EvaluationAttemptRepository(Protocol):
    def save(self, attempt: EvaluationAttemptRecord) -> EvaluationAttemptRecord: ...

    def get(self, workspace_id: str, attempt_id: UUID) -> EvaluationAttemptRecord | None: ...

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[EvaluationAttemptRecord]: ...


@dataclass
class InMemoryEvaluationAttemptRepository:
    records: dict[tuple[str, UUID], EvaluationAttemptRecord] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def save(self, attempt: EvaluationAttemptRecord) -> EvaluationAttemptRecord:
        with self.lock:
            self.records[(attempt.workspace_id, attempt.id)] = attempt
        return attempt

    def get(self, workspace_id: str, attempt_id: UUID) -> EvaluationAttemptRecord | None:
        with self.lock:
            return self.records.get((workspace_id, attempt_id))

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[EvaluationAttemptRecord]:
        with self.lock:
            return sorted(
                (record for (scope, _), record in self.records.items() if scope == workspace_id),
                key=lambda record: record.started_at,
                reverse=True,
            )[:limit]


class SqliteEvaluationAttemptRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluation_attempts (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.store.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_evaluation_attempts_workspace
            ON evaluation_attempts(workspace_id, updated_at)
            """
        )

    def save(self, attempt: EvaluationAttemptRecord) -> EvaluationAttemptRecord:
        self.store.execute(
            """
            INSERT INTO evaluation_attempts (id, workspace_id, status, updated_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at,
                payload = excluded.payload
            """,
            (
                str(attempt.id),
                attempt.workspace_id,
                attempt.status.value,
                attempt.updated_at.isoformat(),
                json.dumps(_to_dict(attempt), sort_keys=True),
            ),
        )
        return attempt

    def get(self, workspace_id: str, attempt_id: UUID) -> EvaluationAttemptRecord | None:
        row = self.store.query_one(
            "SELECT payload FROM evaluation_attempts WHERE workspace_id = ? AND id = ?",
            (workspace_id, str(attempt_id)),
        )
        return _from_dict(json.loads(row["payload"])) if row else None

    def list_recent(self, workspace_id: str, limit: int = 20) -> list[EvaluationAttemptRecord]:
        rows = self.store.query(
            """
            SELECT payload FROM evaluation_attempts
            WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?
            """,
            (workspace_id, limit),
        )
        return [_from_dict(json.loads(row["payload"])) for row in rows]


def _to_dict(attempt: EvaluationAttemptRecord) -> dict[str, object]:
    value = asdict(attempt)
    value["id"] = str(attempt.id)
    value["status"] = attempt.status.value
    value["run_id"] = str(attempt.run_id) if attempt.run_id else None
    value["started_at"] = attempt.started_at.isoformat()
    value["completed_at"] = attempt.completed_at.isoformat() if attempt.completed_at else None
    value["updated_at"] = attempt.updated_at.isoformat()
    return value


def _from_dict(value: dict[str, object]) -> EvaluationAttemptRecord:
    return EvaluationAttemptRecord(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        requested_by=str(value["requested_by"]),
        dataset_id=str(value["dataset_id"]),
        dataset_version=str(value["dataset_version"]),
        documents_requested=int(value["documents_requested"]),
        status=EvaluationAttemptStatus(str(value["status"])),
        documents_processed=int(value.get("documents_processed", 0)),
        provider_calls=int(value.get("provider_calls", 0)),
        run_id=UUID(str(value["run_id"])) if value.get("run_id") else None,
        error_code=str(value["error_code"]) if value.get("error_code") else None,
        error_message=str(value["error_message"]) if value.get("error_message") else None,
        started_at=datetime.fromisoformat(str(value["started_at"])),
        completed_at=(
            datetime.fromisoformat(str(value["completed_at"]))
            if value.get("completed_at")
            else None
        ),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )
