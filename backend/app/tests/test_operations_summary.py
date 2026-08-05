from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from decimal import Decimal

from app.documents.jobs import JobStatus
from app.operations.models import EvaluationRunRecord, ProviderRates
from app.operations.service import InvalidOperationsData, OperationsSummaryService


class RecordingOperationsRepository:
    def __init__(
        self,
        counts: Mapping[JobStatus, int],
        runs: Sequence[EvaluationRunRecord],
    ) -> None:
        self.counts = counts
        self.runs = runs
        self.count_request: tuple[str, tuple[JobStatus, ...]] | None = None
        self.run_request: tuple[str, int] | None = None

    def count_processing_jobs_by_status(
        self,
        workspace_id: str,
        statuses: tuple[JobStatus, ...],
    ) -> Mapping[JobStatus, int]:
        self.count_request = (workspace_id, statuses)
        return self.counts

    def list_recent_evaluation_runs(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> Sequence[EvaluationRunRecord]:
        self.run_request = (workspace_id, limit)
        return self.runs[:limit]


class OperationsSummaryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.run = EvaluationRunRecord(
            run_id="eval-12",
            scenario_count=25,
            mean_field_match=0.96,
            validation_accuracy=0.92,
            provider_input_units=1_000,
            provider_output_units=200,
        )
        self.rates = ProviderRates(
            input_unit=Decimal("0.000002"),
            output_unit=Decimal("0.000008"),
        )

    def test_summary_uses_aggregate_counts_and_one_bounded_evaluation_query(self) -> None:
        repository = RecordingOperationsRepository(
            counts={
                JobStatus.QUEUED: 3,
                JobStatus.PROCESSING: 2,
                JobStatus.COMPLETED: 11,
                JobStatus.FAILED: 1,
            },
            runs=[self.run],
        )
        service = OperationsSummaryService(repository, self.rates)

        first = service.summarize("finance")
        second = service.summarize("finance")

        self.assertEqual(first, second)
        self.assertEqual(first.processing.queued, 3)
        self.assertEqual(first.processing.retry, 0)
        self.assertEqual(first.processing.total, 17)
        self.assertEqual(first.latest_evaluation.estimated_provider_cost, Decimal("0.003600"))
        self.assertEqual(repository.count_request[0], "finance")
        self.assertEqual(set(repository.count_request[1]), set(JobStatus))
        self.assertEqual(repository.run_request, ("finance", 1))

    def test_summary_allows_no_evaluation_runs(self) -> None:
        repository = RecordingOperationsRepository({}, [])

        summary = OperationsSummaryService(repository, self.rates).summarize("finance")

        self.assertIsNone(summary.latest_evaluation)
        self.assertEqual(summary.processing.total, 0)

    def test_summary_rejects_invalid_repository_data(self) -> None:
        repository = RecordingOperationsRepository({JobStatus.FAILED: -1}, [self.run])

        with self.assertRaisesRegex(InvalidOperationsData, "must not be negative"):
            OperationsSummaryService(repository, self.rates).summarize("finance")


if __name__ == "__main__":
    unittest.main()
