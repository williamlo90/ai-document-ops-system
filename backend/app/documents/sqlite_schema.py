from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


_BASE_SCHEMA = """
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
    lease_token TEXT,
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
    idempotency_key TEXT,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backoffice_work_items_workspace
    ON backoffice_work_items(workspace_id, updated_at);
CREATE TABLE IF NOT EXISTS backoffice_task_plans (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    work_item_id TEXT NOT NULL,
    idempotency_key TEXT,
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

_QUERY_INDEXES = """
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_backoffice_work_items_idempotency
    ON backoffice_work_items(workspace_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_backoffice_task_plans_idempotency
    ON backoffice_task_plans(workspace_id, work_item_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_BASE_SCHEMA)
    _migrate_schema_columns(connection)
    _backfill_backoffice_idempotency_keys(connection)
    _validate_backoffice_idempotency_uniqueness(connection)
    connection.executescript(_QUERY_INDEXES)
    _record_schema_migrations(connection)
    connection.commit()


def normalize_invoice_identity(value: str | None) -> str:
    return "".join(character for character in (value or "").casefold() if character.isalnum())


def _migrate_schema_columns(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)")}
    if "workspace_id" not in columns:
        connection.execute(
            "ALTER TABLE documents ADD COLUMN workspace_id TEXT NOT NULL DEFAULT 'default'"
        )
    if "submitted_by" not in columns:
        connection.execute(
            "ALTER TABLE documents ADD COLUMN submitted_by TEXT NOT NULL DEFAULT 'admin'"
        )
    if "size_bytes" not in columns:
        connection.execute("ALTER TABLE documents ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0")
    job_columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "next_attempt_at" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN next_attempt_at TEXT")
    if "lease_token" not in job_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN lease_token TEXT")
    work_item_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(backoffice_work_items)")
    }
    if "idempotency_key" not in work_item_columns:
        connection.execute("ALTER TABLE backoffice_work_items ADD COLUMN idempotency_key TEXT")
    plan_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(backoffice_task_plans)")
    }
    if "idempotency_key" not in plan_columns:
        connection.execute("ALTER TABLE backoffice_task_plans ADD COLUMN idempotency_key TEXT")


def _record_schema_migrations(connection: sqlite3.Connection) -> None:
    applied_at = datetime.now(UTC).isoformat()
    for version in (2, 3, 4, 5, 6, 7, 9):
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, applied_at),
        )
    _backfill_invoice_identities(connection)
    _backfill_work_item_documents(connection)
    for version in (10, 11, 12):
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, applied_at),
        )


def _backfill_invoice_identities(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT e.document_id, e.payload
        FROM extractions e
        LEFT JOIN invoice_identities i ON i.document_id = e.document_id
        WHERE i.document_id IS NULL
        """
    )
    values: list[tuple[object, object, object]] = []
    for row in rows:
        data = json.loads(row["payload"]).get("data", {})
        vendor_identity = normalize_invoice_identity(data.get("vendor_name"))
        invoice_identity = normalize_invoice_identity(data.get("invoice_number"))
        if vendor_identity and invoice_identity:
            values.append((row["document_id"], vendor_identity, invoice_identity))
    connection.executemany(
        """
        INSERT OR REPLACE INTO invoice_identities
        (document_id, vendor_identity, invoice_identity) VALUES (?, ?, ?)
        """,
        values,
    )


def _backfill_work_item_documents(connection: sqlite3.Connection) -> None:
    document_ids = {row["id"] for row in connection.execute("SELECT id FROM documents")}
    rows = connection.execute(
        """
        SELECT id, workspace_id, updated_at, payload
        FROM backoffice_work_items
        WHERE id NOT IN (SELECT DISTINCT work_item_id FROM backoffice_work_item_documents)
        """
    )
    values: list[tuple[object, object, object, object]] = []
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
    connection.executemany(
        """
        INSERT OR REPLACE INTO backoffice_work_item_documents
        (work_item_id, workspace_id, document_id, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        values,
    )


def _backfill_backoffice_idempotency_keys(connection: sqlite3.Connection) -> None:
    for table_name in ("backoffice_work_items", "backoffice_task_plans"):
        rows = connection.execute(
            f"SELECT id, payload FROM {table_name} WHERE idempotency_key IS NULL"
        ).fetchall()
        for row in rows:
            value = json.loads(row["payload"]).get("idempotency_key")
            if value:
                connection.execute(
                    f"UPDATE {table_name} SET idempotency_key = ? WHERE id = ?",
                    (str(value), row["id"]),
                )


def _validate_backoffice_idempotency_uniqueness(connection: sqlite3.Connection) -> None:
    checks = (
        (
            "work item",
            """
            SELECT workspace_id, idempotency_key, COUNT(*) AS matches
            FROM backoffice_work_items
            WHERE idempotency_key IS NOT NULL
            GROUP BY workspace_id, idempotency_key
            HAVING matches > 1
            LIMIT 1
            """,
        ),
        (
            "task plan",
            """
            SELECT workspace_id, idempotency_key, COUNT(*) AS matches
            FROM backoffice_task_plans
            WHERE idempotency_key IS NOT NULL
            GROUP BY workspace_id, work_item_id, idempotency_key
            HAVING matches > 1
            LIMIT 1
            """,
        ),
    )
    for label, query in checks:
        duplicate = connection.execute(query).fetchone()
        if duplicate is not None:
            raise RuntimeError(
                f"Duplicate backoffice {label} idempotency keys must be "
                "resolved before this database can be migrated."
            )
