from __future__ import annotations

import sqlite3
from uuid import UUID

from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import DuplicateInvoiceIdentity
from app.documents.sqlite_store import SqliteStore
from app.documents.status import DocumentStatus


class SqliteDocumentRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, document: DocumentRecord) -> None:
        self.store.connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _document_values(document),
        )

    def save(self, document: DocumentRecord) -> None:
        cursor = self.store.connection.execute(
            "UPDATE documents SET workspace_id=?, original_filename=?, storage_key=?, content_type=?, submitted_by=?, size_bytes=?, status=?, created_at=?, updated_at=?, error_message=? WHERE id=?",
            (*_document_values(document)[1:], str(document.id)),
        )
        if cursor.rowcount != 1:
            raise KeyError(document.id)

    def get(self, document_id: UUID) -> DocumentRecord | None:
        row = self.store.connection.execute("SELECT * FROM documents WHERE id=?", (str(document_id),)).fetchone()
        return _row_to_document(row) if row is not None else None

    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]:
        rows = self.store.connection.execute("SELECT * FROM documents WHERE workspace_id=?", (workspace_id,)).fetchall()
        return [_row_to_document(row) for row in rows]

    def reserve_identity(self, workspace_id: str, vendor: str, invoice_number: str) -> None:
        try:
            self.store.connection.execute("INSERT INTO invoice_identities VALUES (?, ?, ?)", (workspace_id, vendor.casefold(), invoice_number.casefold()))
        except sqlite3.IntegrityError as exc:
            raise DuplicateInvoiceIdentity(invoice_number) from exc


class SqliteAuditRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def append(self, event: AuditEvent) -> None:
        self.store.connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(event.id), str(event.document_id), event.event_type, event.actor, event.old_status.value if event.old_status else None, event.new_status.value if event.new_status else None, event.payload_summary, event.created_at.isoformat()),
        )

    def list_for_document(self, document_id: UUID) -> list[AuditEvent]:
        rows = self.store.connection.execute("SELECT * FROM audit_events WHERE document_id=? ORDER BY created_at", (str(document_id),)).fetchall()
        return [AuditEvent(document_id=UUID(row["document_id"]), event_type=row["event_type"], actor=row["actor"], old_status=DocumentStatus(row["old_status"]) if row["old_status"] else None, new_status=DocumentStatus(row["new_status"]) if row["new_status"] else None, payload_summary=row["payload_summary"], id=UUID(row["id"])) for row in rows]


def _document_values(document: DocumentRecord) -> tuple[object, ...]:
    return (str(document.id), document.workspace_id, document.original_filename, document.storage_key, document.content_type, document.submitted_by, document.size_bytes, document.status.value, document.created_at.isoformat(), document.updated_at.isoformat(), document.error_message)


def _row_to_document(row: sqlite3.Row) -> DocumentRecord:
    from datetime import datetime

    return DocumentRecord(original_filename=row["original_filename"], storage_key=row["storage_key"], content_type=row["content_type"], workspace_id=row["workspace_id"], submitted_by=row["submitted_by"], size_bytes=row["size_bytes"], id=UUID(row["id"]), status=DocumentStatus(row["status"]), created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]), error_message=row["error_message"])
