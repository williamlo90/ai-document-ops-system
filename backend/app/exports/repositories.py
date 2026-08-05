from __future__ import annotations

from copy import deepcopy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import RLock
from typing import Protocol, cast
from uuid import UUID

from app.documents.sqlite_repositories import SqliteStore
from app.exports.models import (
    ExportBatchRecord,
    ExportBatchStatus,
    ExportRunRecord,
    ExportRunStatus,
)


class ExportBatchRepository(Protocol):
    def save_batch(self, batch: ExportBatchRecord) -> ExportBatchRecord: ...

    def get_batch(self, workspace_id: str, batch_id: UUID) -> ExportBatchRecord | None: ...

    def list_batches(self, workspace_id: str) -> list[ExportBatchRecord]: ...

    def reserve_run(self, run: ExportRunRecord) -> tuple[ExportRunRecord, bool]: ...

    def save_run(self, run: ExportRunRecord) -> ExportRunRecord: ...

    def get_run(self, workspace_id: str, run_id: UUID) -> ExportRunRecord | None: ...

    def get_run_by_key(self, workspace_id: str, key: str) -> ExportRunRecord | None: ...

    def list_runs(self, workspace_id: str) -> list[ExportRunRecord]: ...


@dataclass
class InMemoryExportBatchRepository:
    batches: dict[tuple[str, UUID], ExportBatchRecord] = field(default_factory=dict)
    runs: dict[tuple[str, UUID], ExportRunRecord] = field(default_factory=dict)
    run_keys: dict[tuple[str, str], UUID] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def save_batch(self, batch: ExportBatchRecord) -> ExportBatchRecord:
        with self.lock:
            stored = deepcopy(batch)
            self.batches[(batch.workspace_id, batch.id)] = stored
        return deepcopy(stored)

    def get_batch(self, workspace_id: str, batch_id: UUID) -> ExportBatchRecord | None:
        with self.lock:
            return deepcopy(self.batches.get((workspace_id, batch_id)))

    def list_batches(self, workspace_id: str) -> list[ExportBatchRecord]:
        with self.lock:
            return deepcopy(
                sorted(
                    (batch for (scope, _), batch in self.batches.items() if scope == workspace_id),
                    key=lambda batch: batch.updated_at,
                    reverse=True,
                )
            )

    def reserve_run(self, run: ExportRunRecord) -> tuple[ExportRunRecord, bool]:
        with self.lock:
            existing_id = self.run_keys.get((run.workspace_id, run.idempotency_key))
            if existing_id is not None:
                return deepcopy(self.runs[(run.workspace_id, existing_id)]), False
            stored = deepcopy(run)
            self.runs[(run.workspace_id, run.id)] = stored
            self.run_keys[(run.workspace_id, run.idempotency_key)] = run.id
            return deepcopy(stored), True

    def save_run(self, run: ExportRunRecord) -> ExportRunRecord:
        with self.lock:
            stored = deepcopy(run)
            self.runs[(run.workspace_id, run.id)] = stored
            self.run_keys[(run.workspace_id, run.idempotency_key)] = run.id
        return deepcopy(stored)

    def get_run(self, workspace_id: str, run_id: UUID) -> ExportRunRecord | None:
        with self.lock:
            return deepcopy(self.runs.get((workspace_id, run_id)))

    def get_run_by_key(self, workspace_id: str, key: str) -> ExportRunRecord | None:
        with self.lock:
            run_id = self.run_keys.get((workspace_id, key))
            return deepcopy(self.runs.get((workspace_id, run_id))) if run_id else None

    def list_runs(self, workspace_id: str) -> list[ExportRunRecord]:
        with self.lock:
            return deepcopy(
                sorted(
                    (run for (scope, _), run in self.runs.items() if scope == workspace_id),
                    key=lambda run: run.created_at,
                    reverse=True,
                )
            )


class SqliteExportBatchRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS export_batches (
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
            CREATE INDEX IF NOT EXISTS idx_export_batches_workspace
            ON export_batches(workspace_id, updated_at)
            """
        )
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS export_runs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (workspace_id, idempotency_key)
            )
            """
        )
        self.store.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_export_runs_workspace
            ON export_runs(workspace_id, updated_at)
            """
        )

    def save_batch(self, batch: ExportBatchRecord) -> ExportBatchRecord:
        self.store.execute(
            """
            INSERT INTO export_batches (id, workspace_id, status, updated_at, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at,
                payload = excluded.payload
            """,
            (
                str(batch.id),
                batch.workspace_id,
                batch.status.value,
                batch.updated_at.isoformat(),
                json.dumps(_batch_to_dict(batch), sort_keys=True),
            ),
        )
        return batch

    def get_batch(self, workspace_id: str, batch_id: UUID) -> ExportBatchRecord | None:
        row = self.store.query_one(
            "SELECT payload FROM export_batches WHERE workspace_id = ? AND id = ?",
            (workspace_id, str(batch_id)),
        )
        return _batch_from_dict(json.loads(row["payload"])) if row else None

    def list_batches(self, workspace_id: str) -> list[ExportBatchRecord]:
        rows = self.store.query(
            "SELECT payload FROM export_batches WHERE workspace_id = ? ORDER BY updated_at DESC",
            (workspace_id,),
        )
        return [_batch_from_dict(json.loads(row["payload"])) for row in rows]

    def reserve_run(self, run: ExportRunRecord) -> tuple[ExportRunRecord, bool]:
        connection = self.store.connection
        with self.store.transaction():
            existing = connection.execute(
                "SELECT payload FROM export_runs WHERE workspace_id = ? AND idempotency_key = ?",
                (run.workspace_id, run.idempotency_key),
            ).fetchone()
            if existing is not None:
                return _run_from_dict(json.loads(existing["payload"])), False
            connection.execute(
                """
                INSERT INTO export_runs
                (id, workspace_id, batch_id, idempotency_key, status, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(run.id),
                    run.workspace_id,
                    str(run.batch_id),
                    run.idempotency_key,
                    run.status.value,
                    run.updated_at.isoformat(),
                    json.dumps(_run_to_dict(run), sort_keys=True),
                ),
            )
            return run, True

    def save_run(self, run: ExportRunRecord) -> ExportRunRecord:
        self.store.execute(
            """
            UPDATE export_runs SET status = ?, updated_at = ?, payload = ? WHERE id = ?
            """,
            (
                run.status.value,
                run.updated_at.isoformat(),
                json.dumps(_run_to_dict(run), sort_keys=True),
                str(run.id),
            ),
        )
        return run

    def get_run(self, workspace_id: str, run_id: UUID) -> ExportRunRecord | None:
        row = self.store.query_one(
            "SELECT payload FROM export_runs WHERE workspace_id = ? AND id = ?",
            (workspace_id, str(run_id)),
        )
        return _run_from_dict(json.loads(row["payload"])) if row else None

    def get_run_by_key(self, workspace_id: str, key: str) -> ExportRunRecord | None:
        row = self.store.query_one(
            "SELECT payload FROM export_runs WHERE workspace_id = ? AND idempotency_key = ?",
            (workspace_id, key),
        )
        return _run_from_dict(json.loads(row["payload"])) if row else None

    def list_runs(self, workspace_id: str) -> list[ExportRunRecord]:
        rows = self.store.query(
            "SELECT payload FROM export_runs WHERE workspace_id = ? ORDER BY updated_at DESC",
            (workspace_id,),
        )
        return [_run_from_dict(json.loads(row["payload"])) for row in rows]


def _batch_to_dict(batch: ExportBatchRecord) -> dict[str, object]:
    value = asdict(batch)
    value["id"] = str(batch.id)
    value["document_ids"] = [str(item) for item in batch.document_ids]
    value["status"] = batch.status.value
    value["last_run_id"] = str(batch.last_run_id) if batch.last_run_id else None
    value["created_at"] = batch.created_at.isoformat()
    value["updated_at"] = batch.updated_at.isoformat()
    return value


def _batch_from_dict(value: dict[str, object]) -> ExportBatchRecord:
    return ExportBatchRecord(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        document_ids=tuple(
            UUID(str(item)) for item in cast(list[object], value.get("document_ids", []))
        ),
        destination=str(value["destination"]),
        export_format=str(value["export_format"]),
        created_by=str(value["created_by"]),
        status=ExportBatchStatus(str(value["status"])),
        name=str(value["name"]) if value.get("name") else None,
        last_run_id=UUID(str(value["last_run_id"])) if value.get("last_run_id") else None,
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )


def _run_to_dict(run: ExportRunRecord) -> dict[str, object]:
    value = asdict(run)
    value["id"] = str(run.id)
    value["batch_id"] = str(run.batch_id)
    value["document_ids"] = [str(item) for item in run.document_ids]
    value["status"] = run.status.value
    value["created_at"] = run.created_at.isoformat()
    value["completed_at"] = run.completed_at.isoformat() if run.completed_at else None
    value["updated_at"] = run.updated_at.isoformat()
    return value


def _run_from_dict(value: dict[str, object]) -> ExportRunRecord:
    return ExportRunRecord(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        batch_id=UUID(str(value["batch_id"])),
        document_ids=tuple(
            UUID(str(item)) for item in cast(list[object], value.get("document_ids", []))
        ),
        idempotency_key=str(value["idempotency_key"]),
        destination=str(value["destination"]),
        export_format=str(value["export_format"]),
        actor=str(value["actor"]),
        status=ExportRunStatus(str(value["status"])),
        attempt_count=int(cast(int | str, value.get("attempt_count", 1))),
        file_name=str(value["file_name"]) if value.get("file_name") else None,
        artifact_content=(
            str(value["artifact_content"]) if value.get("artifact_content") is not None else None
        ),
        error_code=str(value["error_code"]) if value.get("error_code") else None,
        error_message=str(value["error_message"]) if value.get("error_message") else None,
        retryable=bool(value.get("retryable", False)),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        completed_at=(
            datetime.fromisoformat(str(value["completed_at"]))
            if value.get("completed_at")
            else None
        ),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )
