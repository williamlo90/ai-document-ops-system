from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from app.documents.sqlite_repositories import SqliteStore
from app.review.corrections import correction_event_to_dict, invoice_data_from_dict
from app.review.models import (
    CORRECTION_SCHEMA_VERSION,
    CorrectionEvent,
    CorrectionReasonSource,
    CorrectionSource,
    FieldCorrection,
)


class SqliteCorrectionEventRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS correction_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self.store.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_correction_events_document
            ON correction_events(workspace_id, document_id, created_at)
            """
        )
        self.store.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (8, datetime.now().astimezone().isoformat()),
        )

    def add(self, event: CorrectionEvent) -> CorrectionEvent:
        self.store.execute(
            """
            INSERT INTO correction_events (id, workspace_id, document_id, created_at, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                event.workspace_id,
                str(event.document_id),
                event.created_at.isoformat(),
                json.dumps(correction_event_to_dict(event)),
            ),
        )
        return event

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[CorrectionEvent]:
        rows = self.store.query(
            """
            SELECT payload FROM correction_events
            WHERE workspace_id = ? AND document_id = ?
            ORDER BY created_at
            """,
            (workspace_id, str(document_id)),
        )
        return [_event_from_dict(json.loads(row["payload"])) for row in rows]

    def list_by_workspace(self, workspace_id: str) -> list[CorrectionEvent]:
        rows = self.store.query(
            """
            SELECT payload FROM correction_events
            WHERE workspace_id = ?
            ORDER BY created_at
            """,
            (workspace_id,),
        )
        return [_event_from_dict(json.loads(row["payload"])) for row in rows]


def _event_from_dict(value: dict[str, object]) -> CorrectionEvent:
    return CorrectionEvent(
        schema_version=str(value.get("schema_version") or CORRECTION_SCHEMA_VERSION),
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        document_id=UUID(str(value["document_id"])),
        actor=str(value["actor"]),
        reason=str(value["reason"]),
        source=CorrectionSource(str(value["source"])),
        reason_source=CorrectionReasonSource(str(value["reason_source"])),
        original_ai_data=invoice_data_from_dict(_dict(value["original_ai_data"])),
        before_data=invoice_data_from_dict(_dict(value["before_data"])),
        after_data=invoice_data_from_dict(_dict(value["after_data"])),
        changes=tuple(
            FieldCorrection(
                field_path=str(change["field_path"]),
                original_ai_value=change.get("original_ai_value"),
                before_value=change.get("before_value"),
                after_value=change.get("after_value"),
            )
            for change in _dict_list(value.get("changes"))
        ),
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Correction event snapshot must be an object")
    return value


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
