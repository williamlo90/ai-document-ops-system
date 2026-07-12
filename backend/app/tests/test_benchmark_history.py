from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.api.dependencies import build_container
from app.benchmark.history import (
    InMemoryBenchmarkHistoryRepository,
    SqliteBenchmarkHistoryRepository,
)
from app.core.settings import Settings
from app.documents.repositories import NotFoundError
from app.documents.sqlite_repositories import SqliteStore


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

if __name__ == "__main__":
    unittest.main()
