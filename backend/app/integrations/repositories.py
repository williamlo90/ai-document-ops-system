from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import UUID

from app.documents.sqlite_repositories import SqliteStore
from app.integrations.models import IntegrationDeliveryRecord, IntegrationDeliveryStatus


class IntegrationDeliveryRepository(Protocol):
    def reserve(
        self, record: IntegrationDeliveryRecord
    ) -> tuple[IntegrationDeliveryRecord, bool]: ...

    def save(self, record: IntegrationDeliveryRecord) -> IntegrationDeliveryRecord: ...

    def get_by_key(
        self, workspace_id: str, adapter_name: str, idempotency_key: str
    ) -> IntegrationDeliveryRecord | None: ...

    def claim_retry(self, record_id: UUID) -> IntegrationDeliveryRecord | None: ...


@dataclass
class InMemoryIntegrationDeliveryRepository:
    records: dict[tuple[str, str, str], IntegrationDeliveryRecord] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)

    def reserve(self, record: IntegrationDeliveryRecord) -> tuple[IntegrationDeliveryRecord, bool]:
        key = _record_key(record)
        with self.lock:
            existing = self.records.get(key)
            if existing is not None:
                return existing, False
            self.records[key] = record
            return record, True

    def save(self, record: IntegrationDeliveryRecord) -> IntegrationDeliveryRecord:
        with self.lock:
            self.records[_record_key(record)] = record
        return record

    def get_by_key(
        self, workspace_id: str, adapter_name: str, idempotency_key: str
    ) -> IntegrationDeliveryRecord | None:
        with self.lock:
            return self.records.get((workspace_id, adapter_name, idempotency_key))

    def claim_retry(self, record_id: UUID) -> IntegrationDeliveryRecord | None:
        with self.lock:
            for key, record in self.records.items():
                if (
                    record.id == record_id
                    and record.status == IntegrationDeliveryStatus.FAILED
                    and record.retryable
                ):
                    claimed = replace(
                        record,
                        status=IntegrationDeliveryStatus.PENDING,
                        retryable=False,
                        error_code=None,
                        attempt_count=record.attempt_count + 1,
                        updated_at=datetime.now(UTC),
                    )
                    self.records[key] = claimed
                    return claimed
        return None


class SqliteIntegrationDeliveryRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS integration_deliveries (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                adapter_name TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE (workspace_id, adapter_name, idempotency_key)
            )
            """
        )
        self.store.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_integration_deliveries_document
            ON integration_deliveries(workspace_id, document_id, updated_at)
            """
        )

    def reserve(self, record: IntegrationDeliveryRecord) -> tuple[IntegrationDeliveryRecord, bool]:
        connection = self.store.connection
        with self.store.lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT payload FROM integration_deliveries
                    WHERE workspace_id = ? AND adapter_name = ? AND idempotency_key = ?
                    """,
                    (record.workspace_id, record.adapter_name, record.idempotency_key),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return _record_from_dict(json.loads(existing["payload"])), False
                connection.execute(
                    """
                    INSERT INTO integration_deliveries
                    (id, workspace_id, document_id, adapter_name, idempotency_key,
                     status, updated_at, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _record_params(record),
                )
                connection.commit()
                return record, True
            except Exception:
                connection.rollback()
                raise

    def save(self, record: IntegrationDeliveryRecord) -> IntegrationDeliveryRecord:
        self.store.execute(
            """
            UPDATE integration_deliveries
            SET status = ?, updated_at = ?, payload = ?
            WHERE id = ?
            """,
            (
                record.status.value,
                record.updated_at.isoformat(),
                json.dumps(_record_to_dict(record), sort_keys=True),
                str(record.id),
            ),
        )
        return record

    def get_by_key(
        self, workspace_id: str, adapter_name: str, idempotency_key: str
    ) -> IntegrationDeliveryRecord | None:
        row = self.store.query_one(
            """
            SELECT payload FROM integration_deliveries
            WHERE workspace_id = ? AND adapter_name = ? AND idempotency_key = ?
            """,
            (workspace_id, adapter_name, idempotency_key),
        )
        return _record_from_dict(json.loads(row["payload"])) if row is not None else None

    def claim_retry(self, record_id: UUID) -> IntegrationDeliveryRecord | None:
        connection = self.store.connection
        with self.store.lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT payload FROM integration_deliveries WHERE id = ?",
                    (str(record_id),),
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                record = _record_from_dict(json.loads(row["payload"]))
                if record.status != IntegrationDeliveryStatus.FAILED or not record.retryable:
                    connection.commit()
                    return None
                claimed = replace(
                    record,
                    status=IntegrationDeliveryStatus.PENDING,
                    retryable=False,
                    error_code=None,
                    attempt_count=record.attempt_count + 1,
                    updated_at=datetime.now(UTC),
                )
                connection.execute(
                    """
                    UPDATE integration_deliveries
                    SET status = ?, updated_at = ?, payload = ? WHERE id = ?
                    """,
                    (
                        claimed.status.value,
                        claimed.updated_at.isoformat(),
                        json.dumps(_record_to_dict(claimed), sort_keys=True),
                        str(claimed.id),
                    ),
                )
                connection.commit()
                return claimed
            except Exception:
                connection.rollback()
                raise


def _record_key(record: IntegrationDeliveryRecord) -> tuple[str, str, str]:
    return record.workspace_id, record.adapter_name, record.idempotency_key


def _record_params(record: IntegrationDeliveryRecord) -> tuple[str, ...]:
    return (
        str(record.id),
        record.workspace_id,
        str(record.document_id),
        record.adapter_name,
        record.idempotency_key,
        record.status.value,
        record.updated_at.isoformat(),
        json.dumps(_record_to_dict(record), sort_keys=True),
    )


def _record_to_dict(record: IntegrationDeliveryRecord) -> dict[str, object]:
    value = asdict(record)
    value["id"] = str(record.id)
    value["document_id"] = str(record.document_id)
    value["status"] = record.status.value
    value["created_at"] = record.created_at.isoformat()
    value["updated_at"] = record.updated_at.isoformat()
    return value


def _record_from_dict(value: dict[str, object]) -> IntegrationDeliveryRecord:
    return IntegrationDeliveryRecord(
        id=UUID(str(value["id"])),
        workspace_id=str(value["workspace_id"]),
        document_id=UUID(str(value["document_id"])),
        adapter_name=str(value["adapter_name"]),
        idempotency_key=str(value["idempotency_key"]),
        payload_hash=str(value["payload_hash"]),
        status=IntegrationDeliveryStatus(str(value["status"])),
        external_id=str(value["external_id"]) if value.get("external_id") else None,
        error_code=str(value["error_code"]) if value.get("error_code") else None,
        retryable=bool(value.get("retryable", False)),
        attempt_count=int(value.get("attempt_count", 1)),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
    )
