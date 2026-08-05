from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    scenario_count: int
    mean_field_match: float
    validation_accuracy: float
