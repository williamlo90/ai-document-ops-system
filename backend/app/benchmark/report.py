from __future__ import annotations

from app.benchmark.datasets import DATASET_VERSION
from app.benchmark.metrics import BenchmarkMetrics


def report(metrics: BenchmarkMetrics) -> dict[str, object]:
    return {"dataset_version": DATASET_VERSION, "scenario_count": metrics.scenario_count, "field_match": metrics.mean_field_match, "validation_accuracy": metrics.validation_accuracy}
