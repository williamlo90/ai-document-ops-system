from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from app.documents.sqlite_repositories import job_from_row
from app.invoices.queries import (
    InvoiceListPage,
    InvoiceListQuery,
    SqliteInvoiceQueryRepository,
    _invoice_page,
)
from app.metrics.queries import JobMetrics, MetricsSnapshot
from app.operations.queries import JobHealthSnapshot
from app.postgres.store import PostgresStore
from app.providers.queries import ProviderActivity


class PostgresInvoiceQueryRepository(SqliteInvoiceQueryRepository):
    def list(self, query: InvoiceListQuery) -> InvoiceListPage:
        common_sql, common_params = self._common_query(query)
        filters, filter_params = self._filters(query)
        filtered_sql = f"{common_sql}, filtered AS (SELECT * FROM base {filters})"
        order_expression = {
            "created": "created_at",
            "invoice_date": "invoice_date",
            "vendor": "LOWER(vendor_name)",
            "amount": "total_amount::numeric",
            "updated": "updated_at",
        }[query.sort]
        direction = "ASC" if query.direction == "asc" else "DESC"
        offset = (query.page - 1) * query.page_size
        rows = self.store.query(
            f"""{filtered_sql}
            SELECT id, workspace_id, original_filename, storage_key, content_type,
                   submitted_by, size_bytes, status, created_at, updated_at, error_message
            FROM filtered ORDER BY {order_expression} {direction}, id {direction}
            LIMIT ? OFFSET ?""",
            (*common_params, *filter_params, query.page_size, offset),
        )
        total = self.store.query_one(
            f"{filtered_sql} SELECT COUNT(*) AS count FROM filtered",
            (*common_params, *filter_params),
        )
        summary = self.store.query_one(
            f"""{common_sql} SELECT COUNT(*) AS all_count,
                COUNT(*) FILTER (WHERE business_status = 'needs_review') AS waiting_review,
                COUNT(*) FILTER (WHERE business_status = 'needs_correction') AS needs_correction,
                COUNT(*) FILTER (WHERE business_status = 'approved') AS approved,
                COUNT(*) FILTER (WHERE business_status = 'exported') AS exported FROM base""",
            common_params,
        )
        insights = self.store.query_one(
            f"""{common_sql} SELECT
                COUNT(*) FILTER (WHERE extraction_payload IS NOT NULL
                    AND jsonb_array_length(extraction_payload::jsonb->'validation') > 0) AS flagged,
                COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM
                    jsonb_array_elements(extraction_payload::jsonb->'validation') issue
                    WHERE LOWER(issue->>'code') LIKE '%duplicate%')) AS duplicates_suspected,
                COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM
                    jsonb_array_elements(extraction_payload::jsonb->'validation') issue
                    WHERE LOWER(issue->>'code') LIKE '%tax%')) AS tax_amount_issues
                FROM base""",
            common_params,
        )
        if total is None or summary is None or insights is None:
            raise RuntimeError("Invoice query did not return aggregate rows")
        return _invoice_page(
            cast(Any, rows), cast(Any, total), cast(Any, summary), cast(Any, insights)
        )

    def _common_query(self, query: InvoiceListQuery) -> tuple[str, tuple[object, ...]]:
        owner_filter = "AND d.submitted_by = ?" if query.owner_user_id else ""
        params: list[object] = [query.workspace_id, query.workspace_id]
        if query.owner_user_id:
            params.append(query.owner_user_id)
        return (
            f"""
            WITH latest_links AS (
                SELECT document_id, work_item_id,
                       ROW_NUMBER() OVER (PARTITION BY document_id
                           ORDER BY updated_at DESC, work_item_id DESC) AS position
                FROM backoffice_work_item_documents WHERE workspace_id = ?
            ), base_values AS (
                SELECT d.*, e.payload AS extraction_payload, w.payload AS work_item_payload,
                       e.payload::jsonb->'data'->>'vendor_name' AS vendor_name,
                       e.payload::jsonb->'data'->>'invoice_number' AS invoice_number,
                       e.payload::jsonb->'data'->>'invoice_date' AS invoice_date,
                       e.payload::jsonb->'data'->>'total' AS total_amount,
                       EXISTS (SELECT 1 FROM jsonb_array_elements(
                           COALESCE(e.payload::jsonb->'validation', '[]'::jsonb)) issue
                           WHERE issue->>'severity' = 'error') AS has_errors,
                       w.payload::jsonb->'business_context'->>'correction_state' AS correction_state
                FROM documents d LEFT JOIN extractions e ON e.document_id = d.id
                LEFT JOIN latest_links links ON links.document_id = d.id AND links.position = 1
                LEFT JOIN backoffice_work_items w ON w.id = links.work_item_id
                WHERE d.workspace_id = ? {owner_filter}
            ), base AS (
                SELECT *, CASE WHEN status = 'failed' THEN 'needs_correction'
                    WHEN status = 'needs_review' AND (has_errors OR correction_state = 'requested')
                    THEN 'needs_correction' ELSE status END AS business_status FROM base_values
            )
            """,
            tuple(params),
        )


class PostgresMetricsQueryRepository:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def summary(self, workspace_id: str) -> MetricsSnapshot:
        document_rows = self.store.query(
            "SELECT status, COUNT(*) AS records FROM documents WHERE workspace_id = ? GROUP BY status",
            (workspace_id,),
        )
        job_rows = self.store.query(
            """
            SELECT j.status, j.provider_name, COUNT(*) AS records,
                   SUM(CASE WHEN j.status = 'succeeded' AND j.started_at IS NOT NULL
                            AND j.finished_at IS NOT NULL
                            AND j.finished_at::timestamptz >= j.started_at::timestamptz
                       THEN EXTRACT(EPOCH FROM (j.finished_at::timestamptz - j.started_at::timestamptz)) * 1000
                       ELSE 0 END) AS duration_total_ms,
                   SUM(CASE WHEN j.status = 'succeeded' AND j.started_at IS NOT NULL
                            AND j.finished_at IS NOT NULL
                            AND j.finished_at::timestamptz >= j.started_at::timestamptz
                       THEN 1 ELSE 0 END) AS duration_count
            FROM jobs j JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ? GROUP BY j.status, j.provider_name
            """,
            (workspace_id,),
        )
        audit_rows = self.store.query(
            """SELECT a.event_type, COUNT(*) AS records FROM audit_events a
               JOIN documents d ON d.id = a.document_id
               WHERE d.workspace_id = ? GROUP BY a.event_type""",
            (workspace_id,),
        )
        by_status = _counts_by(document_rows, "status")
        job_metrics = _job_metrics(job_rows)
        audit_counts = _counts_by(audit_rows, "event_type")
        return MetricsSnapshot(
            documents_total=sum(by_status.values()),
            jobs_total=job_metrics["jobs_total"],
            audit_events_total=sum(audit_counts.values()),
            by_status=by_status,
            queue=job_metrics["queue"],
            provider_failures=job_metrics["provider_failures"],
            provider_runs=job_metrics["provider_runs"],
            correction_count=audit_counts.get("extraction_updated", 0),
            review_saved_count=audit_counts.get("review_saved", 0),
            succeeded_jobs=job_metrics["succeeded_jobs"],
            average_processing_time_ms=job_metrics["average_processing_time_ms"],
        )


class PostgresProviderHealthQueryRepository:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def summary(self, workspace_id: str) -> dict[str, ProviderActivity]:
        rows = self.store.query(
            """
            SELECT j.provider_name, COUNT(*) AS observed_runs,
                   COUNT(*) FILTER (WHERE j.status IN ('failed', 'dead_letter')) AS observed_failures
            FROM jobs j JOIN documents d ON d.id = j.document_id
            WHERE d.workspace_id = ? AND j.provider_name IS NOT NULL GROUP BY j.provider_name
            """,
            (workspace_id,),
        )
        return {
            str(row["provider_name"]): ProviderActivity(
                observed_runs=int(row["observed_runs"]),
                observed_failures=int(row["observed_failures"]),
            )
            for row in rows
        }


class PostgresOperationsQueryRepository:
    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def job_health(
        self,
        workspace_id: str,
        *,
        stalled_before: datetime,
        failure_offset: int = 0,
        failure_limit: int = 100,
    ) -> JobHealthSnapshot:
        counts = self.store.query_one(
            """
            SELECT COUNT(*) FILTER (WHERE j.status IN ('queued', 'retrying')) AS queued_jobs,
                   COUNT(*) FILTER (WHERE j.status IN ('failed', 'dead_letter')) AS failed_jobs,
                   COUNT(*) FILTER (WHERE j.status = 'running' AND j.updated_at < ?) AS stalled_jobs
            FROM jobs j JOIN documents d ON d.id = j.document_id WHERE d.workspace_id = ?
            """,
            (stalled_before.isoformat(), workspace_id),
        )
        if counts is None:
            raise RuntimeError("Operational job query did not return an aggregate row")
        rows = self.store.query(
            """SELECT j.* FROM jobs j JOIN documents d ON d.id = j.document_id
               WHERE d.workspace_id = ? AND j.status IN ('failed', 'dead_letter')
               ORDER BY j.updated_at DESC, j.id DESC LIMIT ? OFFSET ?""",
            (workspace_id, failure_limit, failure_offset),
        )
        return JobHealthSnapshot(
            queued_jobs=int(counts["queued_jobs"]),
            failed_jobs=int(counts["failed_jobs"]),
            stalled_jobs=int(counts["stalled_jobs"]),
            failures=tuple(job_from_row(cast(Any, row)) for row in rows),
        )


def _counts_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return {str(row[field]): int(row["records"]) for row in rows}


def _job_metrics(rows: list[dict[str, Any]]) -> JobMetrics:
    queue = {
        key: 0 for key in ("queued", "running", "retrying", "failed", "dead_letter", "succeeded")
    }
    provider_runs: dict[str, int] = {}
    jobs_total = provider_failures = succeeded_jobs = duration_count = 0
    duration_total_ms = 0.0
    for row in rows:
        status, records = str(row["status"]), int(row["records"])
        jobs_total += records
        if status in queue:
            queue[status] += records
        if status in {"failed", "dead_letter"}:
            provider_failures += records
        if status == "succeeded":
            succeeded_jobs += records
        if row["provider_name"]:
            name = str(row["provider_name"])
            provider_runs[name] = provider_runs.get(name, 0) + records
        duration_total_ms += float(row["duration_total_ms"] or 0)
        duration_count += int(row["duration_count"] or 0)
    return {
        "jobs_total": jobs_total,
        "queue": queue,
        "provider_failures": provider_failures,
        "provider_runs": provider_runs,
        "succeeded_jobs": succeeded_jobs,
        "average_processing_time_ms": float(
            round(duration_total_ms / duration_count) if duration_count else 0
        ),
    }
