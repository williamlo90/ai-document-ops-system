from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.documents.jobs import ProcessingJob
from app.documents.sqlite_repositories import SqliteStore, job_from_row


@dataclass(frozen=True)
class JobHealthSnapshot:
    queued_jobs: int
    failed_jobs: int
    stalled_jobs: int
    failures: tuple[ProcessingJob, ...]


class OperationsQueryRepository(Protocol):
    def job_health(
        self,
        workspace_id: str,
        *,
        stalled_before: datetime,
        failure_offset: int = 0,
        failure_limit: int = 100,
    ) -> JobHealthSnapshot: ...


class SqliteOperationsQueryRepository:
    """Bounded operational reads for processing-job monitoring."""

    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def job_health(
        self,
        workspace_id: str,
        *,
        stalled_before: datetime,
        failure_offset: int = 0,
        failure_limit: int = 100,
    ) -> JobHealthSnapshot:
        counts = self.store.query_one(
            """
            SELECT
                SUM(j.status IN ('queued', 'retrying')) AS queued_jobs,
                SUM(j.status IN ('failed', 'dead_letter')) AS failed_jobs,
                SUM(j.status = 'running' AND j.updated_at < ?) AS stalled_jobs
            FROM jobs j
            JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ?
            """,
            (stalled_before.isoformat(), workspace_id),
        )
        if counts is None:
            raise RuntimeError("Operational job query did not return an aggregate row")
        failure_rows = self.store.query(
            """
            SELECT j.*
            FROM jobs j
            JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ? AND j.status IN ('failed', 'dead_letter')
            ORDER BY j.updated_at DESC, j.id DESC
            LIMIT ? OFFSET ?
            """,
            (workspace_id, failure_limit, failure_offset),
        )
        return JobHealthSnapshot(
            queued_jobs=int(counts["queued_jobs"] or 0),
            failed_jobs=int(counts["failed_jobs"] or 0),
            stalled_jobs=int(counts["stalled_jobs"] or 0),
            failures=tuple(job_from_row(row) for row in failure_rows),
        )
