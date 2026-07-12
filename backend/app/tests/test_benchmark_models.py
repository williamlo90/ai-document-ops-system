from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.benchmark.models import (
    EvaluationDataset,
    EvaluationDocument,
    ProviderRunResult,
    BenchmarkRun,
    dataset_from_fixtures,
    run_results_to_predicted_records,
)


class EvaluationDocumentTests(unittest.TestCase):
    def test_constructs_with_fields(self) -> None:
        doc = EvaluationDocument(
            document_id="inv-001",
            expected_fields={"vendor_name": "Acme", "total": "100.00"},
        )
        self.assertEqual(doc.document_id, "inv-001")
        self.assertEqual(doc.expected_fields["vendor_name"], "Acme")

    def test_allows_none_field_values(self) -> None:
        doc = EvaluationDocument(
            document_id="inv-002",
            expected_fields={"vendor_name": None, "total": None},
        )
        self.assertIsNone(doc.expected_fields["vendor_name"])


class EvaluationDatasetTests(unittest.TestCase):
    def test_constructs_with_documents(self) -> None:
        docs = (
            EvaluationDocument("a", {"total": "100"}),
            EvaluationDocument("b", {"total": "200"}),
        )
        ds = EvaluationDataset(name="test", documents=docs)
        self.assertEqual(ds.name, "test")
        self.assertEqual(len(ds.documents), 2)

    def test_empty_dataset(self) -> None:
        ds = EvaluationDataset(name="empty", documents=())
        self.assertEqual(len(ds.documents), 0)


class ProviderRunResultTests(unittest.TestCase):
    def test_success_result(self) -> None:
        result = ProviderRunResult(
            document_id="inv-001",
            provider_name="mock+mock",
            predicted_fields={"total": "100.00"},
            latency_ms=12.5,
            trace_id="trace-1",
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.latency_ms, 12.5)

    def test_error_result(self) -> None:
        result = ProviderRunResult(
            document_id="inv-001",
            provider_name="mock+mock",
            predicted_fields={},
            latency_ms=0.0,
            error="Provider failed: mock+mock",
        )
        self.assertEqual(result.error, "Provider failed: mock+mock")


class BenchmarkRunTests(unittest.TestCase):
    def test_full_run(self) -> None:
        now = datetime.now(timezone.utc)
        results = (
            ProviderRunResult("a", "mock", {"total": "100"}, 10.0),
            ProviderRunResult("b", "mock", {"total": "200"}, 20.0),
        )
        run = BenchmarkRun(
            dataset_name="test",
            provider_name="mock+mock",
            results=results,
            started_at=now,
            finished_at=now,
        )
        self.assertEqual(len(run.results), 2)


class DatasetFromFixturesTests(unittest.TestCase):
    def test_converts_records(self) -> None:
        records = [
            {"document_id": "inv-001", "vendor_name": "Acme", "total": "100.00"},
            {"document_id": "inv-002", "vendor_name": "Beta", "total": "200.00"},
        ]
        ds = dataset_from_fixtures("test", records)
        self.assertEqual(ds.name, "test")
        self.assertEqual(len(ds.documents), 2)
        self.assertEqual(ds.documents[0].document_id, "inv-001")
        self.assertEqual(ds.documents[0].expected_fields["vendor_name"], "Acme")


class RunResultsToPredictedRecordsTests(unittest.TestCase):
    def test_converts_results(self) -> None:
        results = (
            ProviderRunResult("a", "mock", {"total": "100", "tax": "10"}, 5.0),
            ProviderRunResult("b", "mock", {"total": "200", "tax": "0"}, 5.0),
        )
        records = run_results_to_predicted_records(results)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["document_id"], "a")
        self.assertEqual(records[0]["total"], "100")
        self.assertEqual(records[1]["tax"], "0")


if __name__ == "__main__":
    unittest.main()
