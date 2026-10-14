from __future__ import annotations

import json
from typing import Any
from contextlib import contextmanager
from copy import deepcopy
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS ap_scope_locks (
 workspace_id TEXT PRIMARY KEY, epoch INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS ap_versions (
 workspace_id TEXT NOT NULL, kind TEXT NOT NULL, entity_id TEXT NOT NULL,
 version INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (workspace_id, kind, entity_id, version)
);
"""


class VersionRepository:
    """Append-only records. Shared DB transaction and workspace lock serialize writers."""

    def __init__(self, store: Any = None) -> None:
        self.store = store
        self._rows = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self, workspace):
        if self.store is None:
            with self._lock:
                before = deepcopy(self._rows)
                try:
                    yield
                except Exception:
                    self._rows = before
                    raise
        else:
            with self.store.transaction():
                self.store.execute(
                    "INSERT INTO ap_scope_locks (workspace_id, epoch) VALUES (?, 0) ON CONFLICT (workspace_id) DO NOTHING",
                    (workspace,),
                )
                self.store.execute(
                    "UPDATE ap_scope_locks SET epoch = epoch + 1 WHERE workspace_id = ?",
                    (workspace,),
                )
                yield

    def history(self, workspace, kind, entity_id):
        if self.store is None:
            with self._lock:
                return deepcopy(self._rows.get((workspace, kind, entity_id), []))
        return [
            json.loads(row["payload"])
            for row in self.store.query(
                "SELECT payload FROM ap_versions WHERE workspace_id = ? AND kind = ? AND entity_id = ? ORDER BY version",
                (workspace, kind, entity_id),
            )
        ]

    def latest(self, workspace, kind, entity_id):
        rows = self.history(workspace, kind, entity_id)
        return rows[-1] if rows else None

    def append(self, workspace, kind, entity_id, payload):
        rows = self.history(workspace, kind, entity_id)
        payload = deepcopy(payload)
        payload["version"] = len(rows) + 1
        if self.store is None:
            self._rows.setdefault((workspace, kind, entity_id), []).append(payload)
        else:
            self.store.execute(
                "INSERT INTO ap_versions (workspace_id, kind, entity_id, version, payload) VALUES (?, ?, ?, ?, ?)",
                (
                    workspace,
                    kind,
                    entity_id,
                    payload["version"],
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return deepcopy(payload)

    def latest_for_document(self, workspace, kind, document_id):
        if self.store is None:
            rows = [
                r
                for (w, k, _), history in self._rows.items()
                if w == workspace and k == kind
                for r in history
            ]
        else:
            rows = [
                json.loads(r["payload"])
                for r in self.store.query(
                    "SELECT payload FROM ap_versions WHERE workspace_id = ? AND kind = ?",
                    (workspace, kind),
                )
            ]
        matching = [r for r in rows if r.get("document_id") == str(document_id)]
        return deepcopy(max(matching, key=lambda r: r["at"])) if matching else None
