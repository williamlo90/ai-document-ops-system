from __future__ import annotations

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from app.documents.sqlite_store import SqliteStore


class V1RuntimeIsolationTests(unittest.TestCase):
    def test_rejects_v2_database_before_schema_or_journal_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.sqlite3"
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("CREATE TABLE ap_versions (id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO ap_versions VALUES ('preserved')")
                connection.commit()
            before = path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "V2 AP schema detected"):
                SqliteStore(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])

    def test_separate_v1_database_can_be_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.sqlite3"
            store = SqliteStore(path)
            store.close()
            store = SqliteStore(path)
            try:
                self.assertEqual(store.execute("SELECT count(*) FROM documents").fetchone()[0], 0)
            finally:
                store.close()
