from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol, TypedDict

from app.documents.sqlite_repositories import SqliteStore


@dataclass(frozen=True)
class MetricsSnapshot:
    documents_total: int
    jobs_total: int
    audit_events_total: int
    by_status: dict[str, int]
    queue: dict[str, int]
    provider_failures: int
    provider_runs: dict[str, int]
    correction_count: int
    review_saved_count: int
    succeeded_jobs: int
    average_processing_time_ms: float


class JobMetrics(TypedDict):
    jobs_total: int
    queue: dict[str, int]
    provider_failures: int
    provider_runs: dict[str, int]
    succeeded_jobs: int
    average_processing_time_ms: float


class MetricsQueryRepository(Protocol):
    def summary(self, workspace_id: str) -> MetricsSnapshot: ...


class SqliteMetricsQueryRepository:
    """Read-only aggregate queries for the operational metrics endpoint."""

    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def summary(self, workspace_id: str) -> MetricsSnapshot:
        document_rows = self.store.query(
            """
            SELECT status, COUNT(*) AS records
            FROM documents
            WHERE workspace_id = ?
            GROUP BY status
            """,
            (workspace_id,),
        )
        job_rows = self.store.query(
            """
            SELECT j.status,
                   j.provider_name,
                   COUNT(*) AS records,
                   SUM(
                       CASE
                           WHEN j.status = 'succeeded'
                                AND j.started_at IS NOT NULL
                                AND j.finished_at IS NOT NULL
                                 AND unixepoch(j.finished_at, 'subsec')
                                     >= unixepoch(j.started_at, 'subsec')
                            THEN (
                                unixepoch(j.finished_at, 'subsec')
                                - unixepoch(j.started_at, 'subsec')
                            ) * 1000.0
                           ELSE 0
                       END
                   ) AS duration_total_ms,
                   SUM(
                       CASE
                           WHEN j.status = 'succeeded'
                                AND j.started_at IS NOT NULL
                                AND j.finished_at IS NOT NULL
                                 AND unixepoch(j.finished_at, 'subsec')
                                     >= unixepoch(j.started_at, 'subsec')
                           THEN 1
                           ELSE 0
                       END
                   ) AS duration_count
            FROM jobs j
            JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ?
            GROUP BY j.status, j.provider_name
            """,
            (workspace_id,),
        )
        audit_rows = self.store.query(
            """
            SELECT a.event_type, COUNT(*) AS records
            FROM audit_events a
            JOIN documents d ON d.id = a.document_id
            WHERE d.workspace_id = ?
            GROUP BY a.event_type
            """,
            (workspace_id,),
        )

        by_status = self._counts_by(document_rows, "status")
        job_metrics = self._job_metrics(job_rows)
        audit_counts = self._counts_by(audit_rows, "event_type")
        return MetricsSnapshot(
            documents_total=sum(by_status.values()),
            jobs_total=job_metrics["jobs_total"],
            audit_events_total=sum(audit_counts.values()),
            by_status=by_status,
            queue=job_metrics["queue"],
            provider_failures=job_metrics["provider_failures"],
            provider_runs=job_metrics["provider_runs"],
            correction_count=audit_counts.get("extraction_updated", 0),
            review_saved_count=audit_counts.get("review_saved", 0),
            succeeded_jobs=job_metrics["succeeded_jobs"],
            average_processing_time_ms=job_metrics["average_processing_time_ms"],
        )

    @staticmethod
    def _counts_by(rows: list[sqlite3.Row], field: str) -> dict[str, int]:
        return {str(row[field]): int(row["records"]) for row in rows}

    @staticmethod
    def _job_metrics(job_rows: list[sqlite3.Row]) -> JobMetrics:
        queue = {
            "queued": 0,
            "running": 0,
            "retrying": 0,
            "failed": 0,
            "dead_letter": 0,
            "succeeded": 0,
        }
        provider_runs: dict[str, int] = {}
        jobs_total = 0
        provider_failures = 0
        succeeded_jobs = 0
        duration_total_ms = 0.0
        duration_count = 0
        for row in job_rows:
            status = str(row["status"])
            records = int(row["records"])
            jobs_total += records
            if status in queue:
                queue[status] += records
            if status in {"failed", "dead_letter"}:
                provider_failures += records
            if status == "succeeded":
                succeeded_jobs += records
            provider_name = row["provider_name"]
            if provider_name:
                name = str(provider_name)
                provider_runs[name] = provider_runs.get(name, 0) + records
            duration_total_ms += float(row["duration_total_ms"] or 0.0)
            duration_count += int(row["duration_count"] or 0)
        return {
            "jobs_total": jobs_total,
            "queue": queue,
            "provider_failures": provider_failures,
            "provider_runs": provider_runs,
            "succeeded_jobs": succeeded_jobs,
            "average_processing_time_ms": float(
                round(duration_total_ms / duration_count) if duration_count else 0
            ),
        }
