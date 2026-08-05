from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from app.benchmark.datasets import Scenario
from app.benchmark.metrics import BenchmarkMetrics


@runtime_checkable
class EvaluationRunnerPort(Protocol):
    def run(self, scenarios: Sequence[Scenario]) -> BenchmarkMetrics: ...


@runtime_checkable
class OperationsSnapshotPort(Protocol):
    def snapshot(self) -> Mapping[str, int | float | str]: ...
