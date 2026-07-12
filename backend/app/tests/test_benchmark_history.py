from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.api.dependencies import build_container
from app.benchmark.history import (
    InMemoryBenchmarkHistoryRepository,
    SqliteBenchmarkHistoryRepository,
)
from app.core.settings import Settings
from app.documents.repositories import NotFoundError
from app.documents.sqlite_repositories import SqliteStore
from app.ui import _comparison_report_from_history, _provider_cards


def _report(provider: str = "mock_parser+mock_extractor") -> dict:
    return {
        "report_version": "1.0",
        "dataset": "simple_two",
        "providers_count": 1,
        "ranking": [
            {
                "rank": 1,
                "provider": provider,
                "field_accuracy": 0.75,
                "document_success_rate": 0.5,
                "provider_error_rate": 0,
                "estimated_cost_total": 0,
                "average_latency_ms": 0,
            }
        ],
        "providers": [],
        "limitations": [],
    }


class BenchmarkHistoryTests(unittest.TestCase):
    def test_memory_history_saves_gets_and_lists_recent(self) -> None:
        repo = InMemoryBenchmarkHistoryRepository()
        older = repo.save("simple_two", "mock", _report())
        newer = repo.save("pdf_sample", "mock", _report("mock_parser+mock_extractor"))

        self.assertEqual(repo.count(), 2)
        self.assertEqual(repo.get(older.id).dataset_name, "simple_two")
        self.assertEqual(len(repo.list_recent(limit=1)), 1)
        self.assertEqual({record.id for record in repo.list_recent(limit=2)}, {older.id, newer.id})

    def test_memory_history_unknown_run_is_not_found(self) -> None:
        repo = InMemoryBenchmarkHistoryRepository()
        saved = repo.save("simple_two", "mock", _report())

        with self.assertRaises(NotFoundError):
            repo.get(saved.id.__class__("00000000-0000-0000-0000-000000000000"))

    def test_sqlite_history_survives_store_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "doc_intel.sqlite3"
            store = SqliteStore(db_path)
            repo = SqliteBenchmarkHistoryRepository(store)
            saved = repo.save("pdf_sample", "mock", _report())
            store.connection.close()

            recreated_store = SqliteStore(db_path)
            recreated_repo = SqliteBenchmarkHistoryRepository(recreated_store)
            loaded = recreated_repo.get(saved.id)
            recreated_store.connection.close()

        self.assertEqual(loaded.dataset_name, "pdf_sample")
        self.assertEqual(loaded.provider_name, "mock")
        self.assertEqual(loaded.report["ranking"][0]["field_accuracy"], 0.75)

    def test_container_exposes_history_for_memory_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_container = build_container(
                Settings(
                    app_env="test",
                    admin_token="test-token",
                    upload_root=Path(temp_dir) / "memory-uploads",
                    max_upload_bytes=1000,
                    storage_backend="memory",
                )
            )
            memory_container.benchmark_history.save("simple_two", "mock", _report())
            self.assertEqual(memory_container.benchmark_history.count(), 1)

            sqlite_container = build_container(
                Settings(
                    app_env="test",
                    admin_token="test-token",
                    upload_root=Path(temp_dir) / "uploads",
                    max_upload_bytes=1000,
                    storage_backend="sqlite",
                    sqlite_path=Path(temp_dir) / "doc_intel.sqlite3",
                )
            )
            sqlite_container.benchmark_history.save("simple_two", "mock", _report())
            self.assertEqual(sqlite_container.benchmark_history.count(), 1)
            sqlite_container.documents.store.connection.close()

    def test_comparison_report_from_history_uses_latest_provider_per_dataset(self) -> None:
        current_report = _comparison_report(
            "simple_two", _provider_summary("mock_parser+mock_extractor", 0.5)
        )
        real_report = _comparison_report(
            "simple_two", _provider_summary("mistral_ocr+llm_json", 1.0)
        )
        other_dataset_report = _comparison_report(
            "pdf_sample", _provider_summary("other_provider", 1.0)
        )
        container = SimpleNamespace(
            benchmark_history=SimpleNamespace(
                list_recent=lambda limit: [
                    SimpleNamespace(dataset_name="simple_two", report=real_report),
                    SimpleNamespace(dataset_name="pdf_sample", report=other_dataset_report),
                ]
            )
        )

        report = _comparison_report_from_history(container, "simple_two", current_report)

        self.assertEqual(report["providers_count"], 2)
        self.assertEqual(report["ranking"][0]["provider"], "mistral_ocr+llm_json")
        self.assertNotIn("other_provider", {item["provider"] for item in report["providers"]})

    def test_provider_card_does_not_hide_stale_mismatch_details(self) -> None:
        html = _provider_cards([_provider_summary("mock_parser+mock_extractor", 0.125)])

        self.assertIn("Field accuracy", html)
        self.assertIn("12.50%", html)
        self.assertIn("Failure details unavailable", html)
        self.assertNotIn("No field mismatches in this run.", html)


def _comparison_report(dataset: str, provider: dict) -> dict:
    return {
        "report_version": "1.0",
        "dataset": dataset,
        "providers_count": 1,
        "ranking": [{**provider, "rank": 1}],
        "providers": [provider],
        "limitations": [],
    }


def _provider_summary(provider: str, accuracy: float) -> dict:
    return {
        "provider": provider,
        "provider_mode": "mock" if "mock" in provider else "real",
        "documents_count": 1,
        "field_accuracy": accuracy,
        "document_success_rate": accuracy,
        "missing_field_rate": 1 - accuracy,
        "provider_error_rate": 0.0,
        "invalid_schema_rate": 0.0,
        "average_latency_ms": 10.0,
        "estimated_cost_total": 0.0 if "mock" in provider else 0.01,
        "estimated_cost_per_document": 0.0 if "mock" in provider else 0.01,
        "failure_examples": [],
        "provider_errors": [],
    }


if __name__ == "__main__":
    unittest.main()
