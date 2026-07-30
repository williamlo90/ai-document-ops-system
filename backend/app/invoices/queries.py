from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.documents.models import DocumentRecord
from app.documents.sqlite_repositories import SqliteStore, document_from_row


@dataclass(frozen=True)
class InvoiceListQuery:
    workspace_id: str
    search: str = ""
    status: str = ""
    vendor: str = ""
    submitted_by: str = ""
    owner_user_id: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    invoice_date_from: date | None = None
    invoice_date_to: date | None = None
    sort: str = "updated"
    direction: str = "desc"
    page: int = 1
    page_size: int = 10


@dataclass(frozen=True)
class InvoiceListPage:
    documents: tuple[DocumentRecord, ...]
    total: int
    summary: dict[str, int]
    insights: dict[str, int]


class InvoiceQueryRepository(Protocol):
    def list(self, query: InvoiceListQuery) -> InvoiceListPage: ...


class SqliteInvoiceQueryRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def list(self, query: InvoiceListQuery) -> InvoiceListPage:
        common_sql, common_params = self._common_query(query)
        filters, filter_params = self._filters(query)
        filtered_sql = f"{common_sql}, filtered AS (SELECT * FROM base {filters})"
        order_expression = {
            "created": "created_at",
            "invoice_date": "invoice_date",
            "vendor": "vendor_name COLLATE NOCASE",
            "amount": "CAST(total_amount AS REAL)",
            "updated": "updated_at",
        }[query.sort]
        direction = "ASC" if query.direction == "asc" else "DESC"
        offset = (query.page - 1) * query.page_size
        rows = self.store.query(
            f"""
            {filtered_sql}
            SELECT id, workspace_id, original_filename, storage_key, content_type,
                   submitted_by, size_bytes, status, created_at, updated_at, error_message
            FROM filtered
            ORDER BY {order_expression} {direction}, id {direction}
            LIMIT ? OFFSET ?
            """,
            (*common_params, *filter_params, query.page_size, offset),
        )
        total_row = self.store.query_one(
            f"{filtered_sql} SELECT COUNT(*) AS count FROM filtered",
            (*common_params, *filter_params),
        )
        summary_row = self.store.query_one(
            f"""
            {common_sql}
            SELECT COUNT(*) AS all_count,
                   SUM(business_status = 'needs_review') AS waiting_review,
                   SUM(business_status = 'needs_correction') AS needs_correction,
                   SUM(business_status = 'approved') AS approved,
                   SUM(business_status = 'exported') AS exported
            FROM base
            """,
            common_params,
        )
        insights_row = self.store.query_one(
            f"""
            {common_sql}
            SELECT
                SUM(
                    extraction_payload IS NOT NULL
                    AND json_array_length(
                        json_extract(extraction_payload, '$.validation')
                    ) > 0
                ) AS flagged,
                SUM(
                    EXISTS (
                        SELECT 1
                        FROM json_each(extraction_payload, '$.validation') issue
                        WHERE LOWER(json_extract(issue.value, '$.code')) LIKE '%duplicate%'
                    )
                ) AS duplicates_suspected,
                SUM(
                    EXISTS (
                        SELECT 1
                        FROM json_each(extraction_payload, '$.validation') issue
                        WHERE LOWER(json_extract(issue.value, '$.code')) LIKE '%tax%'
                    )
                ) AS tax_amount_issues
            FROM base
            """,
            common_params,
        )
        if total_row is None or summary_row is None or insights_row is None:
            raise RuntimeError("Invoice query did not return aggregate rows")
        return _invoice_page(rows, total_row, summary_row, insights_row)

    def _common_query(self, query: InvoiceListQuery) -> tuple[str, tuple[object, ...]]:
        owner_filter = "AND d.submitted_by = ?" if query.owner_user_id else ""
        params: list[object] = [query.workspace_id, query.workspace_id]
        if query.owner_user_id:
            params.append(query.owner_user_id)
        return (
            f"""
            WITH latest_links AS (
                SELECT document_id, work_item_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY document_id
                           ORDER BY updated_at DESC, work_item_id DESC
                       ) AS position
                FROM backoffice_work_item_documents
                WHERE workspace_id = ?
            ),
            base_values AS (
                SELECT d.*,
                       e.payload AS extraction_payload,
                       w.payload AS work_item_payload,
                       json_extract(e.payload, '$.data.vendor_name') AS vendor_name,
                       json_extract(e.payload, '$.data.invoice_number') AS invoice_number,
                       json_extract(e.payload, '$.data.invoice_date') AS invoice_date,
                       json_extract(e.payload, '$.data.total') AS total_amount,
                       EXISTS (
                           SELECT 1
                           FROM json_each(e.payload, '$.validation') issue
                           WHERE json_extract(issue.value, '$.severity') = 'error'
                       ) AS has_errors,
                       json_extract(
                           w.payload, '$.business_context.correction_state'
                       ) AS correction_state
                FROM documents d
                LEFT JOIN extractions e ON e.document_id = d.id
                LEFT JOIN latest_links links
                    ON links.document_id = d.id AND links.position = 1
                LEFT JOIN backoffice_work_items w ON w.id = links.work_item_id
                WHERE d.workspace_id = ? {owner_filter}
            ),
            base AS (
                SELECT *,
                       CASE
                           WHEN status = 'failed' THEN 'needs_correction'
                           WHEN status = 'needs_review'
                                AND (has_errors OR correction_state = 'requested')
                               THEN 'needs_correction'
                           ELSE status
                       END AS business_status
                FROM base_values
            )
            """,
            tuple(params),
        )

    def _filters(self, query: InvoiceListQuery) -> tuple[str, tuple[object, ...]]:
        clauses: list[str] = []
        params: list[object] = []
        if query.search:
            clauses.append(
                """
                LOWER(
                    original_filename || ' ' || COALESCE(vendor_name, '')
                    || ' ' || COALESCE(invoice_number, '')
                ) LIKE ?
                """
            )
            params.append(f"%{query.search.strip().lower()}%")
        if query.status == "open":
            clauses.append(
                "business_status NOT IN ('approved', 'exported', 'rejected', 'cancelled')"
            )
        elif query.status == "completed":
            clauses.append("business_status IN ('approved', 'exported', 'rejected', 'cancelled')")
        elif query.status:
            clauses.append("business_status = ?")
            params.append(query.status)
        if query.vendor:
            clauses.append("LOWER(COALESCE(vendor_name, '')) LIKE ?")
            params.append(f"%{query.vendor.strip().lower()}%")
        if query.submitted_by:
            clauses.append("LOWER(submitted_by) = ?")
            params.append(query.submitted_by.strip().lower())
        if query.created_from:
            clauses.append("DATE(created_at) >= ?")
            params.append(query.created_from.isoformat())
        if query.created_to:
            clauses.append("DATE(created_at) <= ?")
            params.append(query.created_to.isoformat())
        if query.invoice_date_from:
            clauses.append("invoice_date >= ?")
            params.append(query.invoice_date_from.isoformat())
        if query.invoice_date_to:
            clauses.append("invoice_date <= ?")
            params.append(query.invoice_date_to.isoformat())
        prefix = "WHERE " if clauses else ""
        return prefix + " AND ".join(clauses), tuple(params)


def _invoice_page(
    rows: list[sqlite3.Row],
    total_row: sqlite3.Row,
    summary_row: sqlite3.Row,
    insights_row: sqlite3.Row,
) -> InvoiceListPage:
    return InvoiceListPage(
        documents=tuple(document_from_row(row) for row in rows),
        total=int(total_row["count"]),
        summary={
            "all": int(summary_row["all_count"]),
            "waiting_review": int(summary_row["waiting_review"] or 0),
            "needs_correction": int(summary_row["needs_correction"] or 0),
            "approved": int(summary_row["approved"] or 0),
            "exported": int(summary_row["exported"] or 0),
        },
        insights={
            "flagged": int(insights_row["flagged"] or 0),
            "duplicates_suspected": int(insights_row["duplicates_suspected"] or 0),
            "tax_amount_issues": int(insights_row["tax_amount_issues"] or 0),
        },
    )
