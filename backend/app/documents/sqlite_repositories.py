from __future__ import annotations

import sqlite3
import json
from collections.abc import Iterator
from contextlib import contextmanager
from threading import RLock
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import AuditEvent, DocumentRecord, ReviewTask
from app.documents.repositories import NotFoundError, StoredExtraction
from app.documents.status import DocumentStatus
from app.extraction.schemas import FieldConfidence, InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult
from app.validation.invoice import IssueSeverity, ValidationIssue, ValidationReport


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
        self._init_schema()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cursor = self.connection.execute(sql, params)
            if self._transaction_depth == 0:
                self.connection.commit()
            return cursor

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.connection.execute(sql, params))

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.connection.execute(sql, params).fetchone()

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
            self._init_schema_locked()

    def _init_schema_locked(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL DEFAULT 'default',
                original_filename TEXT NOT NULL,
                storage_key TEXT NOT NULL,
                content_type TEXT NOT NULL,
                submitted_by TEXT NOT NULL DEFAULT 'admin',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                provider_name TEXT,
                provider_trace_id TEXT,
                next_attempt_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                payload_summary TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS extractions (
                document_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_tasks (
                document_id TEXT PRIMARY KEY,
                id TEXT NOT NULL,
                status TEXT NOT NULL,
                reviewer_notes TEXT,
                assigned_to TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_identities (
                document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                vendor_identity TEXT NOT NULL,
                invoice_identity TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_invoice_identity_lookup
                ON invoice_identities(vendor_identity, invoice_identity, document_id);
            CREATE TABLE IF NOT EXISTS backoffice_work_item_documents (
                work_item_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (work_item_id, document_id)
            );
            CREATE INDEX IF NOT EXISTS idx_work_item_document_latest
                ON backoffice_work_item_documents(
                    workspace_id, document_id, updated_at DESC, work_item_id
                );
            CREATE TABLE IF NOT EXISTS backoffice_work_items (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_backoffice_work_items_workspace
                ON backoffice_work_items(workspace_id, updated_at);
            CREATE TABLE IF NOT EXISTS backoffice_task_plans (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                work_item_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_backoffice_task_plans_work_item
                ON backoffice_task_plans(workspace_id, work_item_id, created_at);
            CREATE TABLE IF NOT EXISTS backoffice_action_drafts (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                work_item_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_backoffice_action_drafts_work_item
                ON backoffice_action_drafts(workspace_id, work_item_id, created_at);
            CREATE TABLE IF NOT EXISTS backoffice_approvals (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                work_item_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_backoffice_approvals_work_item
                ON backoffice_approvals(workspace_id, work_item_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_backoffice_approvals_pending
                ON backoffice_approvals(workspace_id, status, created_at);
            CREATE TABLE IF NOT EXISTS backoffice_policy_decisions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                work_item_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_backoffice_policy_decisions_work_item
                ON backoffice_policy_decisions(workspace_id, work_item_id, created_at);
            CREATE TABLE IF NOT EXISTS workflow_events (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                document_id TEXT,
                work_item_id TEXT,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workflow_events_document
                ON workflow_events(workspace_id, document_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_events_work_item
                ON workflow_events(workspace_id, work_item_id, created_at);
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_runs_workspace
                ON agent_runs(workspace_id, created_at);
            CREATE TABLE IF NOT EXISTS agentops_evaluations (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                evaluation_type TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agentops_evaluations_workspace
                ON agentops_evaluations(workspace_id, created_at);
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                read_at TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_workspace
                ON notifications(workspace_id, created_at);
            """
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(documents)")}
        if "workspace_id" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'"
            )
        if "submitted_by" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN submitted_by TEXT NOT NULL DEFAULT 'admin'"
            )
        if "size_bytes" not in columns:
            self.connection.execute(
                "ALTER TABLE documents ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0"
            )
        job_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(jobs)")}
        if "next_attempt_at" not in job_columns:
            self.connection.execute("ALTER TABLE jobs ADD COLUMN next_attempt_at TEXT")
        self.connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_documents_workspace_status_updated
                ON documents(workspace_id, status, updated_at DESC, id);
            CREATE INDEX IF NOT EXISTS idx_jobs_processable
                ON jobs(status, next_attempt_at, updated_at, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_jobs_document_created
                ON jobs(document_id, created_at DESC, id);
            CREATE INDEX IF NOT EXISTS idx_audit_document_created
                ON audit_events(document_id, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_review_tasks_status_updated
                ON review_tasks(status, updated_at DESC, document_id);
            """
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (2, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (3, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (4, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (5, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (6, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (7, datetime.now().astimezone().isoformat()),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (9, datetime.now().astimezone().isoformat()),
        )
        self._backfill_invoice_identities()
        self._backfill_work_item_documents()
        self.connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (10, datetime.now(UTC).isoformat()),
        )
        self.connection.commit()

    def _backfill_invoice_identities(self) -> None:
        rows = self.connection.execute(
            """
            SELECT e.document_id, e.payload
            FROM extractions e
            LEFT JOIN invoice_identities i ON i.document_id = e.document_id
            WHERE i.document_id IS NULL
            """
        )
        values = []
        for row in rows:
            data = json.loads(row["payload"]).get("data", {})
            vendor_identity = _identity_text(data.get("vendor_name"))
            invoice_identity = _identity_text(data.get("invoice_number"))
            if vendor_identity and invoice_identity:
                values.append((row["document_id"], vendor_identity, invoice_identity))
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO invoice_identities
            (document_id, vendor_identity, invoice_identity) VALUES (?, ?, ?)
            """,
            values,
        )

    def _backfill_work_item_documents(self) -> None:
        document_ids = {row["id"] for row in self.connection.execute("SELECT id FROM documents")}
        rows = self.connection.execute(
            """
            SELECT id, workspace_id, updated_at, payload
            FROM backoffice_work_items
            WHERE id NOT IN (SELECT DISTINCT work_item_id FROM backoffice_work_item_documents)
            """
        )
        values = []
        for row in rows:
            payload = json.loads(row["payload"])
            values.extend(
                (
                    row["id"],
                    row["workspace_id"],
                    document_id,
                    row["updated_at"],
                )
                for document_id in payload.get("linked_document_ids", [])
                if document_id in document_ids
            )
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO backoffice_work_item_documents
            (work_item_id, workspace_id, document_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            values,
        )


class SqliteDocumentRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, document: DocumentRecord) -> DocumentRecord:
        self.store.execute(
            """
            INSERT INTO documents
            (id, workspace_id, original_filename, storage_key, content_type, submitted_by,
             size_bytes, status, created_at, updated_at, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                original_filename = excluded.original_filename,
                storage_key = excluded.storage_key,
                content_type = excluded.content_type,
                submitted_by = excluded.submitted_by,
                size_bytes = excluded.size_bytes,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                error_message = excluded.error_message
            """,
            _document_params(document),
        )
        return document

    def get(self, document_id: UUID) -> DocumentRecord:
        row = self.store.query_one("SELECT * FROM documents WHERE id = ?", (str(document_id),))
        if row is None:
            raise NotFoundError(f"Document not found: {document_id}")
        return document_from_row(row)

    def list_all(self) -> list[DocumentRecord]:
        return [document_from_row(row) for row in self.store.query("SELECT * FROM documents")]

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        rows = self.store.query(
            "SELECT * FROM documents WHERE workspace_id = ?",
            (workspace_id,),
        )
        return [document_from_row(row) for row in rows]

    def list_by_status(self, status: DocumentStatus) -> list[DocumentRecord]:
        rows = self.store.query("SELECT * FROM documents WHERE status = ?", (status.value,))
        return [document_from_row(row) for row in rows]

    def list_by_workspace_and_status(
        self, workspace_id: str, status: DocumentStatus
    ) -> list[DocumentRecord]:
        rows = self.store.query(
            "SELECT * FROM documents WHERE workspace_id = ? AND status = ?",
            (workspace_id, status.value),
        )
        return [document_from_row(row) for row in rows]


class SqliteJobRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, job: ProcessingJob) -> ProcessingJob:
        self.save(job)
        return job

    def save(self, job: ProcessingJob) -> ProcessingJob:
        self.store.execute(
            """
            INSERT OR REPLACE INTO jobs
            (id, document_id, status, attempt_count, started_at, finished_at, error_message,
             provider_name, provider_trace_id, next_attempt_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _job_params(job),
        )
        return job

    def get(self, job_id: UUID) -> ProcessingJob:
        row = self.store.query_one("SELECT * FROM jobs WHERE id = ?", (str(job_id),))
        if row is None:
            raise NotFoundError(f"Processing job not found: {job_id}")
        return _job_from_row(row)

    def get_latest_for_document(self, document_id: UUID) -> ProcessingJob:
        row = self.store.query_one(
            "SELECT * FROM jobs WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
            (str(document_id),),
        )
        if row is None:
            raise NotFoundError(f"Processing job not found for document: {document_id}")
        return _job_from_row(row)

    def list_all(self) -> list[ProcessingJob]:
        rows = self.store.query("SELECT * FROM jobs")
        return [_job_from_row(row) for row in rows]

    def list_by_status(self, status: ProcessingJobStatus) -> list[ProcessingJob]:
        rows = self.store.query(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at",
            (status.value,),
        )
        return [_job_from_row(row) for row in rows]

    def claim_next_processable(
        self,
        *,
        stale_before: datetime | None = None,
        now: datetime | None = None,
    ) -> ProcessingJob | None:
        connection = self.store.connection
        current = now or datetime.now(UTC)
        with self.store.transaction():
            stale_value = stale_before.isoformat() if stale_before is not None else ""
            row = connection.execute(
                """
                    SELECT * FROM jobs
                    WHERE status = ?
                       OR (
                           status = ?
                           AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                       )
                       OR (status = ? AND ? != '' AND updated_at <= ?)
                    ORDER BY CASE WHEN status = ? THEN 0 ELSE 1 END, created_at
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
            ).fetchone()
            if row is None:
                return None
            job = _job_from_row(row)
            previous_status = job.status.value
            if job.status == ProcessingJobStatus.RUNNING:
                job.retry("worker_lease_expired")
            job.start()
            cursor = connection.execute(
                """
                UPDATE jobs SET status = ?, attempt_count = ?, started_at = ?,
                finished_at = ?, error_message = ?, provider_name = ?,
                provider_trace_id = ?, next_attempt_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    job.status.value,
                    job.attempt_count,
                    job.started_at.isoformat(),
                    None,
                    job.error_message,
                    job.provider_name,
                    job.provider_trace_id,
                    None,
                    job.updated_at.isoformat(),
                    str(job.id),
                    previous_status,
                ),
            )
            return job if cursor.rowcount == 1 else None

    def renew_lease(self, job_id: UUID, *, renewed_at: datetime | None = None) -> bool:
        timestamp = renewed_at or datetime.now(UTC)
        cursor = self.store.execute(
            """
            UPDATE jobs SET updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (
                timestamp.isoformat(),
                str(job_id),
                ProcessingJobStatus.RUNNING.value,
            ),
        )
        return cursor.rowcount == 1

    def count(self) -> int:
        row = self.store.query_one("SELECT COUNT(*) AS count FROM jobs")
        return int(row["count"])


class SqliteAuditRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, event: AuditEvent) -> AuditEvent:
        self.store.execute(
            """
            INSERT OR REPLACE INTO audit_events
            (id, document_id, event_type, actor, old_status, new_status, payload_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                str(event.document_id),
                event.event_type,
                event.actor,
                event.old_status.value if event.old_status else None,
                event.new_status.value if event.new_status else None,
                event.payload_summary,
                _dt(event.created_at),
            ),
        )
        return event

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]:
        rows = self.store.query(
            "SELECT * FROM audit_events WHERE document_id = ? ORDER BY created_at",
            (str(document_id),),
        )
        return [_audit_from_row(row) for row in rows]

    def count(self) -> int:
        row = self.store.query_one("SELECT COUNT(*) AS count FROM audit_events")
        return int(row["count"])


class SqliteExtractionRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(
        self,
        document_id: UUID,
        extraction_result: ExtractionResult,
        validation_report: ValidationReport,
    ) -> StoredExtraction:
        stored = StoredExtraction(document_id, extraction_result, validation_report)
        data = extraction_result.extraction.data
        vendor_identity = _identity_text(data.vendor_name)
        invoice_identity = _identity_text(data.invoice_number)
        with self.store.transaction():
            self.store.execute(
                """
                INSERT INTO extractions (document_id, payload) VALUES (?, ?)
                ON CONFLICT(document_id) DO UPDATE SET payload = excluded.payload
                """,
                (str(document_id), json.dumps(_stored_extraction_to_dict(stored))),
            )
            self.store.execute(
                "DELETE FROM invoice_identities WHERE document_id = ?",
                (str(document_id),),
            )
            if vendor_identity and invoice_identity:
                self.store.execute(
                    """
                    INSERT INTO invoice_identities
                    (document_id, vendor_identity, invoice_identity) VALUES (?, ?, ?)
                    """,
                    (str(document_id), vendor_identity, invoice_identity),
                )
        return stored

    def get_for_document(self, document_id: UUID) -> StoredExtraction:
        row = self.store.query_one(
            "SELECT * FROM extractions WHERE document_id = ?",
            (str(document_id),),
        )
        if row is None:
            raise NotFoundError(f"Extraction not found for document: {document_id}")
        return _stored_extraction_from_dict(json.loads(row["payload"]))

    def get_for_documents(self, document_ids: list[UUID]) -> dict[UUID, StoredExtraction]:
        if not document_ids:
            return {}
        placeholders = ", ".join("?" for _ in document_ids)
        rows = self.store.query(
            f"SELECT payload FROM extractions WHERE document_id IN ({placeholders})",
            tuple(str(document_id) for document_id in document_ids),
        )
        return {
            stored.document_id: stored
            for stored in (_stored_extraction_from_dict(json.loads(row["payload"])) for row in rows)
        }

    def find_by_invoice_identity(
        self,
        vendor_identity: str,
        invoice_identity: str,
    ) -> list[UUID]:
        rows = self.store.query(
            """
            SELECT document_id FROM invoice_identities
            WHERE vendor_identity = ? AND invoice_identity = ?
            """,
            (vendor_identity, invoice_identity),
        )
        return [UUID(row["document_id"]) for row in rows]


class SqliteReviewTaskRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, task: ReviewTask) -> ReviewTask:
        self.store.execute(
            """
            INSERT OR REPLACE INTO review_tasks
            (document_id, id, status, reviewer_notes, assigned_to, reviewed_by, reviewed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(task.document_id),
                str(task.id),
                task.status,
                task.reviewer_notes,
                task.assigned_to,
                task.reviewed_by,
                _dt(task.reviewed_at),
                _dt(task.created_at),
                _dt(task.updated_at),
            ),
        )
        return task

    def get_for_document(self, document_id: UUID) -> ReviewTask:
        row = self.store.query_one(
            "SELECT * FROM review_tasks WHERE document_id = ?",
            (str(document_id),),
        )
        if row is None:
            raise NotFoundError(f"Review task not found for document: {document_id}")
        return _review_from_row(row)

    def list_open(self) -> list[ReviewTask]:
        rows = self.store.query("SELECT * FROM review_tasks WHERE status = 'open'")
        return [_review_from_row(row) for row in rows]


def _document_params(document: DocumentRecord) -> tuple:
    return (
        str(document.id),
        document.workspace_id,
        document.original_filename,
        document.storage_key,
        document.content_type,
        document.submitted_by,
        document.size_bytes,
        document.status.value,
        _dt(document.created_at),
        _dt(document.updated_at),
        document.error_message,
    )


def document_from_row(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        id=UUID(row["id"]),
        workspace_id=row["workspace_id"],
        original_filename=row["original_filename"],
        storage_key=row["storage_key"],
        content_type=row["content_type"],
        submitted_by=row["submitted_by"],
        size_bytes=row["size_bytes"],
        status=DocumentStatus(row["status"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        error_message=row["error_message"],
    )


def _job_params(job: ProcessingJob) -> tuple:
    return (
        str(job.id),
        str(job.document_id),
        job.status.value,
        job.attempt_count,
        _dt(job.started_at),
        _dt(job.finished_at),
        job.error_message,
        job.provider_name,
        job.provider_trace_id,
        _dt(job.next_attempt_at),
        _dt(job.created_at),
        _dt(job.updated_at),
    )


def _job_from_row(row: sqlite3.Row) -> ProcessingJob:
    return ProcessingJob(
        id=UUID(row["id"]),
        document_id=UUID(row["document_id"]),
        status=ProcessingJobStatus(row["status"]),
        attempt_count=row["attempt_count"],
        started_at=_parse_optional_dt(row["started_at"]),
        finished_at=_parse_optional_dt(row["finished_at"]),
        error_message=row["error_message"],
        provider_name=row["provider_name"],
        provider_trace_id=row["provider_trace_id"],
        next_attempt_at=_parse_optional_dt(row["next_attempt_at"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _audit_from_row(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        id=UUID(row["id"]),
        document_id=UUID(row["document_id"]),
        event_type=row["event_type"],
        actor=row["actor"],
        old_status=DocumentStatus(row["old_status"]) if row["old_status"] else None,
        new_status=DocumentStatus(row["new_status"]) if row["new_status"] else None,
        payload_summary=row["payload_summary"],
        created_at=_parse_dt(row["created_at"]),
    )


def _review_from_row(row: sqlite3.Row) -> ReviewTask:
    return ReviewTask(
        id=UUID(row["id"]),
        document_id=UUID(row["document_id"]),
        status=row["status"],
        reviewer_notes=row["reviewer_notes"],
        assigned_to=row["assigned_to"],
        reviewed_by=row["reviewed_by"],
        reviewed_at=_parse_optional_dt(row["reviewed_at"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _stored_extraction_to_dict(stored: StoredExtraction) -> dict:
    data = stored.extraction_result.extraction.data
    return {
        "document_id": str(stored.document_id),
        "provider_name": stored.extraction_result.provider_name,
        "provider_trace_id": stored.extraction_result.provider_trace_id,
        "schema_version": stored.extraction_result.extraction.schema_version,
        "data": {
            "vendor_name": data.vendor_name,
            "invoice_number": data.invoice_number,
            "invoice_date": data.invoice_date.isoformat() if data.invoice_date else None,
            "due_date": data.due_date.isoformat() if data.due_date else None,
            "subtotal": _decimal(data.subtotal),
            "tax": _decimal(data.tax),
            "total": _decimal(data.total),
            "currency": data.currency,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": _decimal(item.quantity),
                    "unit_price": _decimal(item.unit_price),
                    "amount": _decimal(item.amount),
                }
                for item in data.line_items
            ],
        },
        "confidence": [
            {
                "field_name": item.field_name,
                "score": _decimal(item.score),
                "source_page": item.source_page,
                "source_text": item.source_text,
            }
            for item in stored.extraction_result.extraction.confidence
        ],
        "validation": [asdict(item) for item in stored.validation_report.issues],
    }


def _stored_extraction_from_dict(payload: dict) -> StoredExtraction:
    data = payload["data"]
    extraction = InvoiceExtraction(
        schema_version=payload["schema_version"],
        data=InvoiceData(
            vendor_name=data.get("vendor_name"),
            invoice_number=data.get("invoice_number"),
            invoice_date=_parse_date(data.get("invoice_date")),
            due_date=_parse_date(data.get("due_date")),
            subtotal=_parse_decimal(data.get("subtotal")),
            tax=_parse_decimal(data.get("tax")),
            total=_parse_decimal(data.get("total")),
            currency=data.get("currency"),
            line_items=tuple(
                InvoiceLineItem(
                    description=item.get("description"),
                    quantity=_parse_decimal(item.get("quantity")),
                    unit_price=_parse_decimal(item.get("unit_price")),
                    amount=_parse_decimal(item.get("amount")),
                )
                for item in data.get("line_items", [])
            ),
        ),
        confidence=tuple(
            FieldConfidence(
                field_name=item["field_name"],
                score=_parse_decimal(item.get("score")),
                source_page=item.get("source_page"),
                source_text=item.get("source_text"),
            )
            for item in payload.get("confidence", [])
        ),
    )
    report = ValidationReport(
        issues=tuple(
            ValidationIssue(
                field_name=item["field_name"],
                severity=IssueSeverity(item["severity"]),
                code=item["code"],
                message=item["message"],
            )
            for item in payload.get("validation", [])
        )
    )
    return StoredExtraction(
        document_id=UUID(payload["document_id"]),
        extraction_result=ExtractionResult(
            extraction=extraction,
            provider_name=payload["provider_name"],
            provider_trace_id=payload.get("provider_trace_id"),
        ),
        validation_report=report,
    )


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _parse_optional_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _parse_date(value: str | None):
    return datetime.fromisoformat(value).date() if value else None


def _parse_decimal(value: str | None):
    return Decimal(value) if value is not None else None


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _identity_text(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())
