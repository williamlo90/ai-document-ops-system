from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProcessingStatusCounts:
    queued: int = 0
    processing: int = 0
    retry: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0

    @property
    def total(self) -> int:
        return (
            self.queued
            + self.processing
            + self.retry
            + self.completed
            + self.failed
            + self.cancelled
        )


@dataclass(frozen=True, slots=True)
class EvaluationRunRecord:
    run_id: str
    scenario_count: int
    mean_field_match: float
    validation_accuracy: float
    provider_input_units: int
    provider_output_units: int


@dataclass(frozen=True, slots=True)
class EvaluationRunSummary:
    run_id: str
    scenario_count: int
    mean_field_match: float
    validation_accuracy: float
    estimated_provider_cost: Decimal


@dataclass(frozen=True, slots=True)
class ProviderRates:
    input_unit: Decimal
    output_unit: Decimal


@dataclass(frozen=True, slots=True)
class OperationsSummary:
    workspace_id: str
    processing: ProcessingStatusCounts
    latest_evaluation: EvaluationRunSummary | None
