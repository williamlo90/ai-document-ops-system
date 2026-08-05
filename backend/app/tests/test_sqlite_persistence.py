from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.bootstrap.persistence import build_persistence_module
from app.core.settings import Settings
from app.documents.models import DocumentRecord


class SqlitePersistenceTests(unittest.TestCase):
    def test_empty_database_schema_replays_and_document_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "app.sqlite3"
            settings = Settings(persistence_backend="sqlite", sqlite_path=path)
            first = build_persistence_module(settings)
            document = DocumentRecord("invoice.pdf", "key", "application/pdf", workspace_id="alpha")
            with first.transactions.transaction():
                first.documents.add(document)
            first.close()

            second = build_persistence_module(settings)
            try:
                loaded = second.documents.get(document.id)
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.workspace_id, "alpha")  # type: ignore[union-attr]
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
