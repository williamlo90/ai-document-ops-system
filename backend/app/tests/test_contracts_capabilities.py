from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

from app.benchmark.datasets import Scenario
from app.benchmark.metrics import BenchmarkMetrics
from app.contracts import (
    ApprovedInvoiceExporterPort,
    EvaluationRunnerPort,
    ExportReceipt,
    OperationsSnapshotPort,
)


class FakeExporter:
    def export_approved(self, document_id: UUID, *, actor: str, idempotency_key: str) -> ExportReceipt:
        return ExportReceipt(uuid4(), document_id, f"exports/{document_id}.csv", idempotency_key)


class FakeEvaluationRunner:
    def run(self, scenarios: Sequence[Scenario]) -> BenchmarkMetrics:
        return BenchmarkMetrics(len(scenarios), 1.0, 1.0)


class FakeOperationsSnapshot:
    def snapshot(self) -> Mapping[str, int | float | str]:
        return {"status": "operational", "processing": 0}


class CapabilityContractTests(unittest.TestCase):
    def test_export_evaluation_and_operations_ports_are_structural(self) -> None:
        self.assertIsInstance(FakeExporter(), ApprovedInvoiceExporterPort)
        self.assertIsInstance(FakeEvaluationRunner(), EvaluationRunnerPort)
        self.assertIsInstance(FakeOperationsSnapshot(), OperationsSnapshotPort)


if __name__ == "__main__":
    unittest.main()
