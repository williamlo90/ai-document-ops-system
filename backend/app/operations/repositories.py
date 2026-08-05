from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from app.documents.jobs import JobStatus
from app.operations.models import EvaluationRunRecord


class OperationsReadRepository(Protocol):
    """Read model backed by aggregate and explicitly bounded queries."""

    def count_processing_jobs_by_status(
        self,
        workspace_id: str,
        statuses: tuple[JobStatus, ...],
    ) -> Mapping[JobStatus, int]: ...

    def list_recent_evaluation_runs(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> Sequence[EvaluationRunRecord]: ...
