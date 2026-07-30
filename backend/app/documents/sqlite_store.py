from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, cast

from app.documents.sqlite_schema import initialize_schema


class SqliteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), check_same_thread=False, timeout=5.0)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        self._closed = False
        self._transaction_depth = 0
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        try:
            self._init_schema()
        except Exception:
            self.connection.close()
            self._closed = True
            raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.lock:
            cursor = self.connection.execute(sql, params)
            if self._transaction_depth == 0:
                self.connection.commit()
            return cursor

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.connection.execute(sql, params))

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.lock:
            return cast(sqlite3.Row | None, self.connection.execute(sql, params).fetchone())

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            outermost = self._transaction_depth == 0
            savepoint = f"nested_transaction_{self._transaction_depth}"
            if outermost:
                self.connection.execute("BEGIN IMMEDIATE")
            else:
                self.connection.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                self._transaction_depth -= 1
                if outermost:
                    self.connection.rollback()
                else:
                    self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self.connection.commit()
                else:
                    self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")

    def close(self) -> None:
        with self.lock:
            if self._closed:
                return
            self.connection.close()
            self._closed = True

    def _init_schema(self) -> None:
        with self.lock:
            initialize_schema(self.connection)
