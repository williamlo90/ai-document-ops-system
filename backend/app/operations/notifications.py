from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from typing import Protocol
from uuid import UUID, uuid4

from app.documents.repositories import NotFoundError


@dataclass
class Notification:
    workspace_id: str
    source_key: str
    notification_type: str
    title: str
    message: str
    severity: str = "info"
    work_item_id: UUID | None = None
    document_id: UUID | None = None
    read_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = datetime.now(UTC)


class NotificationRepository(Protocol):
    def add(self, notification: Notification) -> Notification: ...
    def save(self, notification: Notification) -> Notification: ...
    def get(self, notification_id: UUID) -> Notification: ...
    def list_recent(self, workspace_id: str, limit: int = 100) -> list[Notification]: ...


@dataclass
class InMemoryNotificationRepository:
    records: dict[UUID, Notification] = field(default_factory=dict)

    def add(self, notification: Notification) -> Notification:
        existing = next(
            (item for item in self.records.values() if item.source_key == notification.source_key),
            None,
        )
        if existing:
            return deepcopy(existing)
        stored = deepcopy(notification)
        self.records[notification.id] = stored
        return deepcopy(stored)

    def save(self, notification: Notification) -> Notification:
        stored = deepcopy(notification)
        self.records[notification.id] = stored
        return deepcopy(stored)

    def get(self, notification_id: UUID) -> Notification:
        try:
            return deepcopy(self.records[notification_id])
        except KeyError as exc:
            raise NotFoundError(f"Notification not found: {notification_id}") from exc

    def list_recent(self, workspace_id: str, limit: int = 100) -> list[Notification]:
        records = [item for item in self.records.values() if item.workspace_id == workspace_id]
        return deepcopy(
            sorted(records, key=lambda item: item.created_at, reverse=True)[: max(limit, 0)]
        )


class SqliteNotificationRepository:
    def __init__(self, store) -> None:
        self.store = store

    def add(self, notification: Notification) -> Notification:
        existing = self.store.query_one(
            "SELECT payload FROM notifications WHERE source_key = ?",
            (notification.source_key,),
        )
        if existing:
            return _from_dict(json.loads(existing["payload"]))
        return self.save(notification)

    def save(self, notification: Notification) -> Notification:
        self.store.execute(
            """
            INSERT OR REPLACE INTO notifications
            (id, workspace_id, source_key, created_at, read_at, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(notification.id),
                notification.workspace_id,
                notification.source_key,
                notification.created_at.isoformat(),
                notification.read_at.isoformat() if notification.read_at else None,
                json.dumps(notification_response(notification)),
            ),
        )
        return notification

    def get(self, notification_id: UUID) -> Notification:
        row = self.store.query_one(
            "SELECT payload FROM notifications WHERE id = ?", (str(notification_id),)
        )
        if row is None:
            raise NotFoundError(f"Notification not found: {notification_id}")
        return _from_dict(json.loads(row["payload"]))

    def list_recent(self, workspace_id: str, limit: int = 100) -> list[Notification]:
        rows = self.store.query(
            """
            SELECT payload FROM notifications
            WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (workspace_id, max(limit, 0)),
        )
        return [_from_dict(json.loads(row["payload"])) for row in rows]


def notification_response(item: Notification) -> dict[str, object]:
    return {
        "id": str(item.id),
        "workspace_id": item.workspace_id,
        "source_key": item.source_key,
        "notification_type": item.notification_type,
        "title": item.title,
        "message": item.message,
        "severity": item.severity,
        "work_item_id": str(item.work_item_id) if item.work_item_id else None,
        "document_id": str(item.document_id) if item.document_id else None,
        "read_at": item.read_at.isoformat() if item.read_at else None,
        "created_at": item.created_at.isoformat(),
    }


def _from_dict(value: dict[str, object]) -> Notification:
    return Notification(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        source_key=str(value["source_key"]),
        notification_type=str(value["notification_type"]),
        title=str(value["title"]),
        message=str(value["message"]),
        severity=str(value["severity"]),
        work_item_id=UUID(str(value["work_item_id"])) if value.get("work_item_id") else None,
        document_id=UUID(str(value["document_id"])) if value.get("document_id") else None,
        read_at=datetime.fromisoformat(str(value["read_at"])) if value.get("read_at") else None,
        created_at=datetime.fromisoformat(str(value["created_at"])),
    )
