from __future__ import annotations

from collections.abc import Mapping

from app.documents.jobs import JobStatus
from app.evaluation.provider_costs import estimate_cost
from app.operations.models import (
    EvaluationRunRecord,
    EvaluationRunSummary,
    OperationsSummary,
    ProcessingStatusCounts,
    ProviderRates,
)
from app.operations.repositories import OperationsReadRepository


PROCESSING_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.PROCESSING,
    JobStatus.RETRY,
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
)


class InvalidOperationsData(ValueError):
    pass


class OperationsSummaryService:
    def __init__(
        self,
        repository: OperationsReadRepository,
        provider_rates: ProviderRates,
    ) -> None:
        self._repository = repository
        self._provider_rates = provider_rates

    def summarize(self, workspace_id: str) -> OperationsSummary:
        if not workspace_id.strip():
            raise ValueError("workspace_id must not be empty")

        raw_counts = self._repository.count_processing_jobs_by_status(
            workspace_id,
            PROCESSING_STATUSES,
        )
        recent_runs = self._repository.list_recent_evaluation_runs(workspace_id, limit=1)
        latest = self._summarize_run(recent_runs[0]) if recent_runs else None

        return OperationsSummary(
            workspace_id=workspace_id,
            processing=self._normalize_counts(raw_counts),
            latest_evaluation=latest,
        )

    @staticmethod
    def _normalize_counts(counts: Mapping[JobStatus, int]) -> ProcessingStatusCounts:
        normalized = {status: counts.get(status, 0) for status in PROCESSING_STATUSES}
        if any(value < 0 for value in normalized.values()):
            raise InvalidOperationsData("processing status counts must not be negative")
        return ProcessingStatusCounts(
            queued=normalized[JobStatus.QUEUED],
            processing=normalized[JobStatus.PROCESSING],
            retry=normalized[JobStatus.RETRY],
            completed=normalized[JobStatus.COMPLETED],
            failed=normalized[JobStatus.FAILED],
            cancelled=normalized[JobStatus.CANCELLED],
        )

    def _summarize_run(self, run: EvaluationRunRecord) -> EvaluationRunSummary:
        if run.scenario_count < 0:
            raise InvalidOperationsData("evaluation scenario count must not be negative")
        if run.provider_input_units < 0 or run.provider_output_units < 0:
            raise InvalidOperationsData("provider usage must not be negative")
        if not 0.0 <= run.mean_field_match <= 1.0:
            raise InvalidOperationsData("field match must be between zero and one")
        if not 0.0 <= run.validation_accuracy <= 1.0:
            raise InvalidOperationsData("validation accuracy must be between zero and one")

        return EvaluationRunSummary(
            run_id=run.run_id,
            scenario_count=run.scenario_count,
            mean_field_match=run.mean_field_match,
            validation_accuracy=run.validation_accuracy,
            estimated_provider_cost=estimate_cost(
                run.provider_input_units,
                run.provider_output_units,
                input_rate=self._provider_rates.input_unit,
                output_rate=self._provider_rates.output_unit,
            ),
        )
