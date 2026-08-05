from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.documents.sqlite_repositories import SqliteStore


@dataclass(frozen=True)
class ProviderActivity:
    observed_runs: int = 0
    observed_failures: int = 0


class ProviderHealthQueryRepository(Protocol):
    def summary(self, workspace_id: str) -> dict[str, ProviderActivity]: ...


class SqliteProviderHealthQueryRepository:
    """Workspace-scoped provider counts without hydrating processing jobs."""

    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def summary(self, workspace_id: str) -> dict[str, ProviderActivity]:
        rows = self.store.query(
            """
            SELECT j.provider_name,
                   COUNT(*) AS observed_runs,
                   SUM(j.status IN ('failed', 'dead_letter')) AS observed_failures
            FROM jobs j
            JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ? AND j.provider_name IS NOT NULL
            GROUP BY j.provider_name
            """,
            (workspace_id,),
        )
        return {
            str(row["provider_name"]): ProviderActivity(
                observed_runs=int(row["observed_runs"]),
                observed_failures=int(row["observed_failures"] or 0),
            )
            for row in rows
        }
