from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.documents.sqlite_repositories import SqliteStore
from app.evaluation.history import (
    EvaluationAttemptRecord,
    EvaluationAttemptStatus,
    SqliteEvaluationAttemptRepository,
)


class EvaluationHistoryTests(unittest.TestCase):
    def test_attempts_survive_restart_and_remain_workspace_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "evaluation.sqlite3"
            store = SqliteStore(database)
            repository = SqliteEvaluationAttemptRepository(store)
            attempt = EvaluationAttemptRecord(
                workspace_id="workspace-a",
                requested_by="reviewer",
                dataset_id="invoice_scenarios_v1",
                dataset_version="1.0",
                documents_requested=3,
            ).failed(documents_processed=1, provider_calls=2)
            repository.save(attempt)
            store.close()

            recreated_store = SqliteStore(database)
            recreated = SqliteEvaluationAttemptRepository(recreated_store)
            restored = recreated.get("workspace-a", attempt.id)

            self.assertIsNotNone(restored)
            self.assertEqual(restored.status, EvaluationAttemptStatus.FAILED)
            self.assertEqual(restored.documents_processed, 1)
            self.assertEqual(restored.provider_calls, 2)
            self.assertEqual(recreated.list_recent("workspace-b"), [])
            recreated_store.close()


if __name__ == "__main__":
    unittest.main()
