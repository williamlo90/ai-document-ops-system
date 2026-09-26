from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from queue import Empty, LifoQueue
from threading import local
from typing import Any

import psycopg
from psycopg.rows import dict_row


class PostgresPoolTimeout(TimeoutError):
    """Raised when every bounded database connection is busy."""


class _Result:
    def __init__(self, *, rowcount: int, row: dict[str, Any] | None = None) -> None:
        self.rowcount = rowcount
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _ConnectionFacade:
    def __init__(self, store: PostgresStore) -> None:
        self._store = store

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _Result:
        return self._store.execute(sql, params, fetch_one=True)

    def close(self) -> None:
        self._store.close()


class PostgresStore:
    """Small bounded psycopg pool with transaction-local connections.

    The facade intentionally matches the subset of ``SqliteStore`` used by the
    repositories. This keeps domain persistence code shared while PostgreSQL-
    specific concurrency and read queries live in dedicated adapters.
    """

    def __init__(
        self,
        database_url: str,
        *,
        pool_size: int = 5,
        connect_timeout_seconds: int = 5,
        acquire_timeout_seconds: float = 5.0,
    ) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL storage")
        if pool_size < 1:
            raise ValueError("DATABASE_POOL_SIZE must be at least 1")
        self.database_url = database_url
        self.pool_size = pool_size
        self.acquire_timeout_seconds = acquire_timeout_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._pool: LifoQueue[psycopg.Connection[dict[str, Any]]] = LifoQueue(pool_size)
        self._local = local()
        self._closed = False
        self.connection = _ConnectionFacade(self)
        try:
            for _ in range(pool_size):
                self._pool.put(self._connect())
        except Exception:
            self.close()
            raise

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(
            self.database_url,
            connect_timeout=self._connect_timeout_seconds,
            row_factory=dict_row,
            autocommit=False,
        )

    @contextmanager
    def _borrow(self) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        active = getattr(self._local, "connection", None)
        if active is not None:
            yield active
            return
        if self._closed:
            raise RuntimeError("PostgreSQL store is closed")
        try:
            connection = self._pool.get(timeout=self.acquire_timeout_seconds)
        except Empty as exc:
            raise PostgresPoolTimeout("Timed out waiting for a PostgreSQL connection") from exc
        try:
            yield connection
        finally:
            if self._closed:
                connection.close()
            else:
                self._pool.put(connection)

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        fetch_one: bool = False,
    ) -> _Result:
        statement = _postgres_sql(sql)
        with self._borrow() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(statement, params)
                    row = cursor.fetchone() if fetch_one and cursor.description else None
                    result = _Result(rowcount=cursor.rowcount, row=row)
                if getattr(self._local, "connection", None) is None:
                    connection.commit()
                return result
            except Exception:
                if getattr(self._local, "connection", None) is None:
                    connection.rollback()
                raise

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._borrow() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(_postgres_sql(sql), params)
                    rows = list(cursor.fetchall())
                if getattr(self._local, "connection", None) is None:
                    connection.commit()
                return rows
            except Exception:
                if getattr(self._local, "connection", None) is None:
                    connection.rollback()
                raise

    def query_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._borrow() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(_postgres_sql(sql), params)
                    row = cursor.fetchone()
                if getattr(self._local, "connection", None) is None:
                    connection.commit()
                return row
            except Exception:
                if getattr(self._local, "connection", None) is None:
                    connection.rollback()
                raise

    @contextmanager
    def transaction(self) -> Iterator[None]:
        active = getattr(self._local, "connection", None)
        if active is not None:
            with active.transaction():
                yield
            return
        with self._borrow() as connection:
            self._local.connection = connection
            try:
                with connection.transaction():
                    yield
            finally:
                self._local.connection = None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        while True:
            try:
                self._pool.get_nowait().close()
            except Empty:
                break


_CONFLICT_KEYS = {
    "agent_runs": ("id",),
    "audit_events": ("id",),
    "backoffice_action_drafts": ("id",),
    "backoffice_approvals": ("id",),
    "backoffice_policy_decisions": ("id",),
    "backoffice_work_item_documents": ("work_item_id", "document_id"),
    "invoice_identities": ("document_id",),
    "notifications": ("id",),
    "review_tasks": ("document_id",),
    "workflow_events": ("id",),
}


def _postgres_sql(sql: str) -> str:
    # psycopg uses percent-style binding, so literal percent characters in
    # shared SQL (for example LIKE '%tax%') must be escaped first.
    statement = sql.replace("%", "%%").replace("?", "%s")
    if re.search(r"INSERT\s+OR\s+IGNORE", statement, flags=re.IGNORECASE):
        return (
            re.sub(
                r"INSERT\s+OR\s+IGNORE",
                "INSERT",
                statement,
                flags=re.IGNORECASE,
            )
            .rstrip()
            .rstrip(";")
            + " ON CONFLICT DO NOTHING"
        )
    match = re.search(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)",
        statement,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return statement
    table = match.group(1).lower()
    columns = [column.strip() for column in match.group(2).split(",")]
    conflict = _CONFLICT_KEYS.get(table)
    if conflict is None:
        raise ValueError(f"No PostgreSQL conflict key registered for table: {table}")
    updates = [column for column in columns if column not in conflict]
    base = (
        re.sub(
            r"INSERT\s+OR\s+REPLACE",
            "INSERT",
            statement,
            count=1,
            flags=re.IGNORECASE,
        )
        .rstrip()
        .rstrip(";")
    )
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in updates)
    return f"{base} ON CONFLICT ({', '.join(conflict)}) DO UPDATE SET {assignments}"
