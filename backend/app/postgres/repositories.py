from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.retention import PurgeRecord, _document_fingerprint
from app.documents.repositories import NotFoundError
from app.documents.sqlite_repositories import SqliteJobRepository, job_from_row
from app.documents.status import DocumentStatus
from app.postgres.store import PostgresStore


class PostgresJobRepository(SqliteJobRepository):
    """Processing jobs with a PostgreSQL row-locking lease claim."""

    def claim_next_processable(
        self,
        *,
        stale_before: datetime | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob | None:
        current = now or datetime.now(UTC)
        stale_value = stale_before.isoformat() if stale_before is not None else ""
        with self.store.transaction():
            row = self.store.query_one(
                """
                SELECT * FROM jobs
                WHERE status = ?
                   OR (status = ? AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
                   OR (status = ? AND ? != '' AND updated_at <= ?)
                ORDER BY CASE WHEN status = ? THEN 0 ELSE 1 END, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (
                    ProcessingJobStatus.QUEUED.value,
                    ProcessingJobStatus.RETRYING.value,
                    current.isoformat(),
                    ProcessingJobStatus.RUNNING.value,
                    stale_value,
                    stale_value,
                    ProcessingJobStatus.RUNNING.value,
                ),
            )
            if row is None:
                return None
            job = job_from_row(cast(Any, row))
            previous_status = job.status.value
            if job.status == ProcessingJobStatus.RUNNING:
                job.retry("worker_lease_expired")
            job.start()
            cursor = self.store.execute(
                """
                UPDATE jobs SET status = ?, attempt_count = ?, started_at = ?,
                    finished_at = ?, error_message = ?, provider_name = ?,
                    provider_trace_id = ?, next_attempt_at = ?, lease_token = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    job.status.value,
                    job.attempt_count,
                    cast(datetime, job.started_at).isoformat(),
                    None,
                    job.error_message,
                    job.provider_name,
                    job.provider_trace_id,
                    None,
                    job.lease_token,
                    job.updated_at.isoformat(),
                    str(job.id),
                    previous_status,
                ),
            )
            return job if cursor.rowcount == 1 else None

    def claim_processable(
        self,
        job_id: UUID,
        *,
        stale_before: datetime | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob | None:
        current = now or datetime.now(UTC)
        with self.store.transaction():
            row = self.store.query_one(
                "SELECT * FROM jobs WHERE id = ? FOR UPDATE SKIP LOCKED",
                (str(job_id),),
            )
            if row is None:
                return None
            job = job_from_row(cast(Any, row))
            processable = (
                job.status == ProcessingJobStatus.QUEUED
                or (
                    job.status == ProcessingJobStatus.RETRYING
                    and (job.next_attempt_at is None or job.next_attempt_at <= current)
                )
                or (
                    stale_before is not None
                    and job.status == ProcessingJobStatus.RUNNING
                    and job.updated_at <= stale_before
                )
            )
            if not processable:
                return None
            previous_status = job.status.value
            if job.status == ProcessingJobStatus.RUNNING:
                job.retry("worker_lease_expired")
            job.start()
            cursor = self.store.execute(
                """
                UPDATE jobs SET status = ?, attempt_count = ?, started_at = ?,
                    finished_at = ?, error_message = ?, provider_name = ?,
                    provider_trace_id = ?, next_attempt_at = ?, lease_token = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    job.status.value,
                    job.attempt_count,
                    cast(datetime, job.started_at).isoformat(),
                    None,
                    job.error_message,
                    job.provider_name,
                    job.provider_trace_id,
                    None,
                    job.lease_token,
                    job.updated_at.isoformat(),
                    str(job.id),
                    previous_status,
                ),
            )
            return job if cursor.rowcount == 1 else None


class PostgresRetentionRepository:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def list_expired(
        self,
        workspace_id: str,
        older_than: datetime,
        statuses: set[DocumentStatus],
    ) -> list[UUID]:
        values = sorted(status.value for status in statuses)
        rows = self.store.query(
            """
            SELECT id FROM documents
            WHERE workspace_id = ? AND created_at < ? AND status = ANY(?)
            ORDER BY created_at
            """,
            (workspace_id, older_than.isoformat(), values),
        )
        return [UUID(str(row["id"])) for row in rows]

    def purge(
        self,
        document_id: UUID,
        workspace_id: str,
        actor: str,
        reason: str,
    ) -> PurgeRecord:
        document_key = str(document_id)
        deleted: dict[str, int] = {}
        with self.store.transaction():
            row = self.store.query_one(
                "SELECT id FROM documents WHERE id = ? AND workspace_id = ? FOR UPDATE",
                (document_key, workspace_id),
            )
            if row is None:
                raise NotFoundError(f"Document not found: {document_id}")
            work_item_ids: list[str] = []
            work_items = self.store.query(
                "SELECT id, payload FROM backoffice_work_items WHERE workspace_id = ?",
                (workspace_id,),
            )
            for item in work_items:
                payload = json.loads(str(item["payload"]))
                linked = [str(value) for value in payload.get("linked_document_ids", [])]
                if document_key not in linked:
                    continue
                remaining = [value for value in linked if value != document_key]
                if remaining:
                    payload["linked_document_ids"] = remaining
                    self.store.execute(
                        "UPDATE backoffice_work_items SET payload = ? WHERE id = ?",
                        (json.dumps(payload), str(item["id"])),
                    )
                else:
                    work_item_ids.append(str(item["id"]))
            for table in ("integration_deliveries", "correction_events"):
                deleted[table] = self.store.execute(
                    f"DELETE FROM {table} WHERE document_id = ?", (document_key,)
                ).rowcount
            deleted["workflow_events"] = self.store.execute(
                "DELETE FROM workflow_events WHERE document_id = ? OR work_item_id = ANY(?)",
                (document_key, work_item_ids),
            ).rowcount
            targets = [document_key, *work_item_ids]
            for table in ("agent_runs", "agentops_evaluations", "notifications"):
                rows = self.store.query(f"SELECT id, payload FROM {table}")
                ids = [
                    str(item["id"])
                    for item in rows
                    if any(target in str(item["payload"]) for target in targets)
                ]
                deleted[table] = self.store.execute(
                    f"DELETE FROM {table} WHERE id = ANY(?)", (ids,)
                ).rowcount
            for table in (
                "backoffice_task_plans",
                "backoffice_action_drafts",
                "backoffice_approvals",
                "backoffice_policy_decisions",
            ):
                deleted[table] = self.store.execute(
                    f"DELETE FROM {table} WHERE work_item_id = ANY(?)", (work_item_ids,)
                ).rowcount
            deleted["backoffice_work_items"] = self.store.execute(
                "DELETE FROM backoffice_work_items WHERE id = ANY(?)", (work_item_ids,)
            ).rowcount
            deleted["documents"] = self.store.execute(
                "DELETE FROM documents WHERE id = ?", (document_key,)
            ).rowcount
            fingerprint = _document_fingerprint(document_id)
            record = PurgeRecord(
                document_fingerprint=fingerprint,
                workspace_id=workspace_id,
                actor=actor,
                reason=reason,
                deleted_records=deleted,
            )
            self.store.execute(
                """
                INSERT INTO data_purge_events
                (id, workspace_id, document_fingerprint, actor, reason, deleted_records, purged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    workspace_id,
                    fingerprint,
                    actor,
                    reason,
                    json.dumps(deleted, sort_keys=True),
                    record.purged_at.isoformat(),
                ),
            )
            return record
