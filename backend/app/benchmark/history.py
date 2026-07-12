from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from app.documents.repositories import NotFoundError


@dataclass(frozen=True)
class BenchmarkHistoryRecord:
    id: UUID
    dataset_name: str
    provider_name: str
    report: dict[str, Any]
    created_at: datetime


class BenchmarkHistoryRepository(Protocol):
    def save(
        self, dataset_name: str, provider_name: str, report: dict[str, Any]
    ) -> BenchmarkHistoryRecord: ...

    def get(self, run_id: UUID) -> BenchmarkHistoryRecord: ...

    def list_recent(self, limit: int = 10) -> list[BenchmarkHistoryRecord]: ...

    def count(self) -> int: ...


@dataclass
class InMemoryBenchmarkHistoryRepository:
    records: dict[UUID, BenchmarkHistoryRecord] = field(default_factory=dict)

    def save(
        self, dataset_name: str, provider_name: str, report: dict[str, Any]
    ) -> BenchmarkHistoryRecord:
        record = BenchmarkHistoryRecord(
            id=uuid4(),
            dataset_name=dataset_name,
            provider_name=provider_name,
            report=report,
            created_at=_now(),
        )
        self.records[record.id] = record
        return record

    def get(self, run_id: UUID) -> BenchmarkHistoryRecord:
        try:
            return self.records[run_id]
        except KeyError as exc:
            raise NotFoundError(f"Benchmark run not found: {run_id}") from exc

    def list_recent(self, limit: int = 10) -> list[BenchmarkHistoryRecord]:
        return sorted(
            self.records.values(),
            key=lambda record: record.created_at,
            reverse=True,
        )[:limit]

    def count(self) -> int:
        return len(self.records)


class SqliteBenchmarkHistoryRepository:
    def __init__(self, store) -> None:
        self.store = store

    def _ensure_schema(self) -> None:
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id TEXT PRIMARY KEY,
                dataset_name TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def save(
        self, dataset_name: str, provider_name: str, report: dict[str, Any]
    ) -> BenchmarkHistoryRecord:
        self._ensure_schema()
        record = BenchmarkHistoryRecord(
            id=uuid4(),
            dataset_name=dataset_name,
            provider_name=provider_name,
            report=report,
            created_at=_now(),
        )
        self.store.execute(
            """
            INSERT INTO benchmark_runs
            (id, dataset_name, provider_name, report_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(record.id),
                record.dataset_name,
                record.provider_name,
                json.dumps(record.report),
                record.created_at.isoformat(),
            ),
        )
        return record

    def get(self, run_id: UUID) -> BenchmarkHistoryRecord:
        try:
            row = self.store.query_one("SELECT * FROM benchmark_runs WHERE id = ?", (str(run_id),))
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                raise NotFoundError(f"Benchmark run not found: {run_id}") from exc
            raise
        if row is None:
            raise NotFoundError(f"Benchmark run not found: {run_id}")
        return _record_from_row(row)

    def list_recent(self, limit: int = 10) -> list[BenchmarkHistoryRecord]:
        try:
            rows = self.store.query(
                "SELECT * FROM benchmark_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return []
            raise
        return [_record_from_row(row) for row in rows]

    def count(self) -> int:
        try:
            row = self.store.query_one("SELECT COUNT(*) AS count FROM benchmark_runs")
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return 0
            raise
        return int(row["count"])


def _record_from_row(row) -> BenchmarkHistoryRecord:
    return BenchmarkHistoryRecord(
        id=UUID(row["id"]),
        dataset_name=row["dataset_name"],
        provider_name=row["provider_name"],
        report=json.loads(row["report_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
