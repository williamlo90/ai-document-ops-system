from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from typing import Protocol
from uuid import UUID, uuid4

from app.core.security import SecurityContext, UnauthorizedError, require_any_role
from app.core.settings import Settings
from app.documents.repositories import DocumentRepository, NotFoundError
from app.documents.sqlite_repositories import SqliteStore
from app.documents.status import DocumentStatus
from app.providers.storage import DocumentStorage


RETENTION_ELIGIBLE_STATUSES = {
    DocumentStatus.APPROVED,
    DocumentStatus.REJECTED,
    DocumentStatus.FAILED,
    DocumentStatus.EXPORTED,
    DocumentStatus.CANCELLED,
}


class RetentionConflict(ValueError):
    pass


@dataclass(frozen=True)
class PurgeRecord:
    document_fingerprint: str
    workspace_id: str
    actor: str
    reason: str
    deleted_records: dict[str, int]
    purged_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RetentionRepository(Protocol):
    def list_expired(
        self,
        workspace_id: str,
        older_than: datetime,
        statuses: set[DocumentStatus],
    ) -> list[UUID]: ...

    def purge(
        self,
        document_id: UUID,
        workspace_id: str,
        actor: str,
        reason: str,
    ) -> PurgeRecord: ...


class DocumentRetentionService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage: DocumentStorage,
        documents: DocumentRepository,
        repository: RetentionRepository,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.documents = documents
        self.repository = repository

    def policy(self, context: SecurityContext) -> dict[str, object]:
        _require_admin(context)
        candidates = self._candidate_ids(context.workspace_id)
        return {
            "document_retention_days": self.settings.document_retention_days,
            "parser_cache_retention_hours": self.settings.parser_cache_retention_hours,
            "eligible_statuses": sorted(status.value for status in RETENTION_ELIGIBLE_STATUSES),
            "candidate_count": len(candidates),
            "candidate_document_ids": [str(value) for value in candidates],
        }

    def purge_document(
        self,
        document_id: UUID,
        context: SecurityContext,
        reason: str,
    ) -> PurgeRecord:
        _require_admin(context)
        document = self.documents.get(document_id)
        if document.workspace_id != context.workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        if document.status in {DocumentStatus.QUEUED, DocumentStatus.PROCESSING}:
            raise RetentionConflict("Cancel active processing before deleting this document")
        normalized_reason = _normalize_reason(reason)
        self.storage.delete(document.storage_key)
        return self.repository.purge(
            document_id,
            context.workspace_id,
            context.actor,
            normalized_reason,
        )

    def purge_expired(
        self,
        context: SecurityContext,
        *,
        dry_run: bool,
        reason: str = "retention_policy",
    ) -> dict[str, object]:
        _require_admin(context)
        candidates = self._candidate_ids(context.workspace_id)
        if dry_run:
            return {
                "dry_run": True,
                "candidate_count": len(candidates),
                "candidate_document_ids": [str(value) for value in candidates],
                "purged_count": 0,
                "cache_files_removed": 0,
            }
        records = [self.purge_document(document_id, context, reason) for document_id in candidates]
        cache_cutoff = datetime.now(UTC) - timedelta(
            hours=self.settings.parser_cache_retention_hours
        )
        cache_removed = self.storage.purge_parser_cache(cache_cutoff)
        return {
            "dry_run": False,
            "candidate_count": len(candidates),
            "candidate_document_ids": [str(value) for value in candidates],
            "purged_count": len(records),
            "cache_files_removed": cache_removed,
            "purges": [purge_record_response(record) for record in records],
        }

    def _candidate_ids(self, workspace_id: str) -> list[UUID]:
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.document_retention_days)
        return self.repository.list_expired(
            workspace_id,
            cutoff,
            RETENTION_ELIGIBLE_STATUSES,
        )


class SqliteRetentionRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store
        self.store.execute(
            """
            CREATE TABLE IF NOT EXISTS data_purge_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                document_fingerprint TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                deleted_records TEXT NOT NULL,
                purged_at TEXT NOT NULL
            )
            """
        )

    def list_expired(
        self,
        workspace_id: str,
        older_than: datetime,
        statuses: set[DocumentStatus],
    ) -> list[UUID]:
        placeholders = ",".join("?" for _ in statuses)
        rows = self.store.query(
            f"""
            SELECT id FROM documents
            WHERE workspace_id = ? AND created_at < ? AND status IN ({placeholders})
            ORDER BY created_at
            """,
            (
                workspace_id,
                older_than.isoformat(),
                *(status.value for status in sorted(statuses, key=lambda value: value.value)),
            ),
        )
        return [UUID(row["id"]) for row in rows]

    def purge(
        self,
        document_id: UUID,
        workspace_id: str,
        actor: str,
        reason: str,
    ) -> PurgeRecord:
        document_key = str(document_id)
        connection = self.store.connection
        deleted: dict[str, int] = {}
        with self.store.lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT id FROM documents WHERE id = ? AND workspace_id = ?",
                    (document_key, workspace_id),
                ).fetchone()
                if row is None:
                    raise NotFoundError(f"Document not found: {document_id}")

                work_item_ids = _unlink_sqlite_work_items(connection, workspace_id, document_key)
                for table in (
                    "backoffice_task_plans",
                    "backoffice_action_drafts",
                    "backoffice_approvals",
                    "backoffice_policy_decisions",
                ):
                    deleted[table] = _delete_for_ids(
                        connection, table, "work_item_id", work_item_ids
                    )
                deleted["backoffice_work_items"] = _delete_for_ids(
                    connection, "backoffice_work_items", "id", work_item_ids
                )
                deleted["workflow_events"] = _delete_workflow_events(
                    connection, document_key, work_item_ids
                )
                deleted["agent_runs"] = _delete_payload_matches(
                    connection,
                    "agent_runs",
                    {document_key, *work_item_ids},
                )
                deleted["agentops_evaluations"] = _delete_payload_matches(
                    connection,
                    "agentops_evaluations",
                    {document_key},
                )
                deleted["notifications"] = _delete_payload_matches(
                    connection,
                    "notifications",
                    {document_key, *work_item_ids},
                )
                for table in (
                    "integration_deliveries",
                    "correction_events",
                    "review_tasks",
                    "extractions",
                    "audit_events",
                    "jobs",
                ):
                    deleted[table] = _delete_for_ids(
                        connection, table, "document_id", {document_key}
                    )
                deleted["documents"] = _delete_for_ids(
                    connection, "documents", "id", {document_key}
                )

                record = PurgeRecord(
                    document_fingerprint=_document_fingerprint(document_id),
                    workspace_id=workspace_id,
                    actor=actor,
                    reason=reason,
                    deleted_records=deleted,
                )
                connection.execute(
                    """
                    INSERT INTO data_purge_events
                    (id, workspace_id, document_fingerprint, actor, reason,
                     deleted_records, purged_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        workspace_id,
                        record.document_fingerprint,
                        actor,
                        reason,
                        json.dumps(deleted, sort_keys=True),
                        record.purged_at.isoformat(),
                    ),
                )
                connection.commit()
                return record
            except Exception:
                connection.rollback()
                raise


class InMemoryRetentionRepository:
    def __init__(self, **repositories: object) -> None:
        self.repositories = repositories
        self.purge_events: list[PurgeRecord] = []

    def list_expired(
        self,
        workspace_id: str,
        older_than: datetime,
        statuses: set[DocumentStatus],
    ) -> list[UUID]:
        documents = self.repositories["documents"]
        records = documents.records
        return sorted(
            (
                document.id
                for document in records.values()
                if document.workspace_id == workspace_id
                and document.created_at < older_than
                and document.status in statuses
            ),
            key=str,
        )

    def purge(
        self,
        document_id: UUID,
        workspace_id: str,
        actor: str,
        reason: str,
    ) -> PurgeRecord:
        deleted: dict[str, int] = {}
        documents = self.repositories["documents"].records
        document = documents.get(document_id)
        if document is None or document.workspace_id != workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")

        work_items = self.repositories["work_items"].records
        removed_work_items: set[UUID] = set()
        for work_item_id, item in list(work_items.items()):
            if document_id not in item.linked_document_ids:
                continue
            remaining = tuple(value for value in item.linked_document_ids if value != document_id)
            if remaining:
                item.linked_document_ids = remaining
            else:
                removed_work_items.add(work_item_id)
                work_items.pop(work_item_id)
        deleted["backoffice_work_items"] = len(removed_work_items)

        _purge_dict_records(
            self.repositories, "jobs", lambda value: value.document_id == document_id, deleted
        )
        _purge_list_records(
            self.repositories, "audits", lambda value: value.document_id == document_id, deleted
        )
        _purge_dict_key(self.repositories, "extractions", document_id, deleted)
        _purge_dict_key(self.repositories, "reviews", document_id, deleted)
        _purge_list_records(
            self.repositories,
            "corrections",
            lambda value: value.document_id == document_id,
            deleted,
        )
        for name in ("plans", "drafts", "approvals"):
            _purge_dict_records(
                self.repositories,
                name,
                lambda value: value.work_item_id in removed_work_items,
                deleted,
            )
        for name in ("policy_decisions", "workflow_events"):
            _purge_list_records(
                self.repositories,
                name,
                lambda value: (
                    getattr(value, "document_id", None) == document_id
                    or getattr(value, "work_item_id", None) in removed_work_items
                ),
                deleted,
            )
        _purge_dict_records(
            self.repositories,
            "agent_runs",
            lambda value: value.work_item_id in removed_work_items,
            deleted,
        )
        _purge_dict_records(
            self.repositories,
            "notifications",
            lambda value: (
                value.document_id == document_id or value.work_item_id in removed_work_items
            ),
            deleted,
        )
        _purge_list_records(
            self.repositories,
            "scenario_evaluations",
            lambda value: value.target_id == str(document_id),
            deleted,
        )
        _purge_dict_records(
            self.repositories,
            "integration_deliveries",
            lambda value: value.document_id == document_id,
            deleted,
        )
        documents.pop(document_id)
        deleted["documents"] = 1
        record = PurgeRecord(
            document_fingerprint=_document_fingerprint(document_id),
            workspace_id=workspace_id,
            actor=actor,
            reason=reason,
            deleted_records=deleted,
        )
        self.purge_events.append(deepcopy(record))
        return deepcopy(record)


def purge_record_response(record: PurgeRecord) -> dict[str, object]:
    return {
        "document_fingerprint": record.document_fingerprint,
        "workspace_id": record.workspace_id,
        "actor": record.actor,
        "reason": record.reason,
        "deleted_records": record.deleted_records,
        "purged_at": record.purged_at.isoformat(),
    }


def validate_retention_policy(settings: Settings) -> None:
    if not 1 <= settings.document_retention_days <= 3_650:
        raise ValueError("DOCUMENT_RETENTION_DAYS must be between 1 and 3650")
    if not 1 <= settings.parser_cache_retention_hours <= 8_760:
        raise ValueError("PARSER_CACHE_RETENTION_HOURS must be between 1 and 8760")


def _require_admin(context: SecurityContext) -> None:
    try:
        require_any_role(context, {"admin"})
    except UnauthorizedError as exc:
        raise UnauthorizedError("Admin role required for retention operations") from exc


def _normalize_reason(reason: str) -> str:
    normalized = " ".join(reason.split())
    if not normalized:
        raise ValueError("Deletion reason is required")
    return normalized[:500]


def _document_fingerprint(document_id: UUID) -> str:
    return sha256(str(document_id).encode("ascii")).hexdigest()[:24]


def _unlink_sqlite_work_items(connection, workspace_id: str, document_id: str) -> set[str]:
    removed: set[str] = set()
    rows = connection.execute(
        "SELECT id, payload FROM backoffice_work_items WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload"])
        linked = [str(value) for value in payload.get("linked_document_ids", [])]
        if document_id not in linked:
            continue
        remaining = [value for value in linked if value != document_id]
        if remaining:
            payload["linked_document_ids"] = remaining
            connection.execute(
                "UPDATE backoffice_work_items SET payload = ? WHERE id = ?",
                (json.dumps(payload), row["id"]),
            )
        else:
            removed.add(str(row["id"]))
    return removed


def _delete_for_ids(connection, table: str, column: str, values: set[str]) -> int:
    if not values or not _table_exists(connection, table):
        return 0
    placeholders = ",".join("?" for _ in values)
    cursor = connection.execute(
        f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
        tuple(values),
    )
    return max(cursor.rowcount, 0)


def _delete_workflow_events(connection, document_id: str, work_item_ids: set[str]) -> int:
    deleted = _delete_for_ids(connection, "workflow_events", "document_id", {document_id})
    deleted += _delete_for_ids(connection, "workflow_events", "work_item_id", work_item_ids)
    return deleted


def _delete_payload_matches(
    connection,
    table: str,
    values: set[str],
) -> int:
    if not values or not _table_exists(connection, table):
        return 0
    rows = connection.execute(f"SELECT id, payload FROM {table}").fetchall()
    ids = {str(row["id"]) for row in rows if any(value in str(row["payload"]) for value in values)}
    return _delete_for_ids(connection, table, "id", ids)


def _table_exists(connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _purge_dict_records(repositories, name, predicate, deleted) -> None:
    records = repositories[name].records
    keys = [key for key, value in records.items() if predicate(value)]
    for key in keys:
        records.pop(key)
    deleted[name] = len(keys)


def _purge_list_records(repositories, name, predicate, deleted) -> None:
    repository = repositories[name]
    records = repository.records
    remaining = [value for value in records if not predicate(value)]
    deleted[name] = len(records) - len(remaining)
    repository.records = remaining


def _purge_dict_key(repositories, name, key, deleted) -> None:
    records = repositories[name].records
    deleted[name] = int(records.pop(key, None) is not None)
