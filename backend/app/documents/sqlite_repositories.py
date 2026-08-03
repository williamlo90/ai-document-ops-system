from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import AuditEvent, DocumentRecord, ReviewTask
from app.documents.repositories import LeaseLostError, NotFoundError, StoredExtraction
from app.documents.sqlite_schema import normalize_invoice_identity as _identity_text
from app.documents.sqlite_store import SqliteStore as SqliteStore
from app.documents.status import DocumentStatus
from app.extraction.schemas import FieldConfidence, InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult
from app.validation.invoice import IssueSeverity, ValidationIssue, ValidationReport


class SqliteDocumentRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def add(self, document: DocumentRecord) -> DocumentRecord:
        return self.save(document)

    def save(self, document: DocumentRecord) -> DocumentRecord:
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

    def save(
        self,
        job: ProcessingJob,
        *,
        expected_lease_token: str | None = None,
    ) -> ProcessingJob:
        if (
            expected_lease_token is None
            and job.status == ProcessingJobStatus.RUNNING
            and job.lease_token is not None
        ):
            existing = self.store.query_one(
                "SELECT status, lease_token FROM jobs WHERE id = ?",
                (str(job.id),),
            )
            if (
                existing is not None
                and existing["status"] == ProcessingJobStatus.RUNNING.value
                and existing["lease_token"] == job.lease_token
            ):
                expected_lease_token = job.lease_token
        if expected_lease_token is not None:
            cursor = self.store.execute(
                """
                UPDATE jobs SET document_id = ?, status = ?, attempt_count = ?,
                    started_at = ?, finished_at = ?, error_message = ?,
                    provider_name = ?, provider_trace_id = ?, next_attempt_at = ?,
                    lease_token = ?, created_at = ?, updated_at = ?
                WHERE id = ? AND lease_token = ? AND status = ?
                """,
                (
                    *_job_params(job)[1:],
                    str(job.id),
                    expected_lease_token,
                    ProcessingJobStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseLostError(f"Processing job lease was lost: {job.id}")
            return job
        cursor = self.store.execute(
            """
            INSERT INTO jobs
            (id, document_id, status, attempt_count, started_at, finished_at, error_message,
             provider_name, provider_trace_id, next_attempt_at, lease_token, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                document_id = excluded.document_id,
                status = excluded.status,
                attempt_count = excluded.attempt_count,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at,
                error_message = excluded.error_message,
                provider_name = excluded.provider_name,
                provider_trace_id = excluded.provider_trace_id,
                next_attempt_at = excluded.next_attempt_at,
                lease_token = excluded.lease_token,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            WHERE jobs.status != 'running' OR jobs.lease_token IS NULL
            """,
            _job_params(job),
        )
        if cursor.rowcount != 1:
            raise LeaseLostError(f"Processing job lease token is required to update: {job.id}")
        return job

    def get(self, job_id: UUID) -> ProcessingJob:
        row = self.store.query_one("SELECT * FROM jobs WHERE id = ?", (str(job_id),))
        if row is None:
            raise NotFoundError(f"Processing job not found: {job_id}")
        return job_from_row(row)

    def get_latest_for_document(self, document_id: UUID) -> ProcessingJob:
        row = self.store.query_one(
            "SELECT * FROM jobs WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
            (str(document_id),),
        )
        if row is None:
            raise NotFoundError(f"Processing job not found for document: {document_id}")
        return job_from_row(row)

    def list_all(self) -> list[ProcessingJob]:
        rows = self.store.query("SELECT * FROM jobs")
        return [job_from_row(row) for row in rows]

    def list_by_status(self, status: ProcessingJobStatus) -> list[ProcessingJob]:
        rows = self.store.query(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at",
            (status.value,),
        )
        return [job_from_row(row) for row in rows]

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
            job = job_from_row(row)
            previous_status = job.status.value
            if job.status == ProcessingJobStatus.RUNNING:
                job.retry("worker_lease_expired")
            job.start()
            cursor = connection.execute(
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

    def renew_lease(
        self,
        job_id: UUID,
        lease_token: str,
        *,
        renewed_at: datetime | None = None,
    ) -> bool:
        timestamp = renewed_at or datetime.now(UTC)
        cursor = self.store.execute(
            """
            UPDATE jobs SET updated_at = ?
            WHERE id = ? AND status = ? AND lease_token = ?
            """,
            (
                timestamp.isoformat(),
                str(job_id),
                ProcessingJobStatus.RUNNING.value,
                lease_token,
            ),
        )
        return cursor.rowcount == 1

    def count(self) -> int:
        row = self.store.query_one("SELECT COUNT(*) AS count FROM jobs")
        assert row is not None
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
        assert row is not None
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


def _document_params(document: DocumentRecord) -> tuple[object, ...]:
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


def _job_params(job: ProcessingJob) -> tuple[object, ...]:
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
        job.lease_token,
        _dt(job.created_at),
        _dt(job.updated_at),
    )


def job_from_row(row: sqlite3.Row) -> ProcessingJob:
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
        lease_token=row["lease_token"],
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


def _stored_extraction_to_dict(stored: StoredExtraction) -> dict[str, Any]:
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


def _stored_extraction_from_dict(payload: dict[str, Any]) -> StoredExtraction:
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
                score=cast(float | None, _parse_decimal(item.get("score"))),
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


def _parse_date(value: str | None) -> date | None:
    return datetime.fromisoformat(value).date() if value else None


def _parse_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _decimal(value: Decimal | float | None) -> str | None:
    return str(value) if value is not None else None
