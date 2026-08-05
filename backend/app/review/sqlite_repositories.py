from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import json
from uuid import UUID

from app.documents.sqlite_store import SqliteStore
from app.extraction.schemas import InvoiceData, InvoiceLineItem
from app.review.models import CorrectionEvent, ReviewRecord


class SqliteReviewRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def save(self, record: ReviewRecord) -> None:
        self.store.connection.execute(
            "INSERT INTO review_records VALUES (?, ?, ?) ON CONFLICT(document_id) DO UPDATE SET original_json=excluded.original_json, current_json=excluded.current_json",
            (str(record.document_id), _encode_invoice(record.original), _encode_invoice(record.current)),
        )

    def get(self, document_id: UUID) -> ReviewRecord | None:
        row = self.store.connection.execute("SELECT * FROM review_records WHERE document_id=?", (str(document_id),)).fetchone()
        return ReviewRecord(document_id, _decode_invoice(row["original_json"]), _decode_invoice(row["current_json"])) if row else None


class SqliteCorrectionRepository:
    def __init__(self, store: SqliteStore) -> None:
        self.store = store

    def append(self, event: CorrectionEvent) -> None:
        self.store.connection.execute("INSERT INTO correction_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (str(event.id), str(event.document_id), event.field_name, event.before, event.after, event.actor, event.reason, event.created_at.isoformat()))

    def list_for_document(self, document_id: UUID) -> list[CorrectionEvent]:
        rows = self.store.connection.execute("SELECT * FROM correction_events WHERE document_id=? ORDER BY created_at", (str(document_id),)).fetchall()
        return [CorrectionEvent(document_id, row["field_name"], row["before_value"], row["after_value"], row["actor"], row["reason"], id=UUID(row["id"]), created_at=datetime.fromisoformat(row["created_at"])) for row in rows]


def _encode_invoice(invoice: InvoiceData) -> str:
    return json.dumps(asdict(invoice), default=str, separators=(",", ":"))


def _decode_invoice(payload: str) -> InvoiceData:
    data = json.loads(payload)
    for name in ("invoice_date", "due_date"):
        if data.get(name):
            data[name] = date.fromisoformat(data[name])
    for name in ("subtotal", "tax", "total"):
        if data.get(name) is not None:
            data[name] = Decimal(data[name])
    data["line_items"] = tuple(InvoiceLineItem(description=item.get("description"), quantity=Decimal(item["quantity"]) if item.get("quantity") is not None else None, unit_price=Decimal(item["unit_price"]) if item.get("unit_price") is not None else None, amount=Decimal(item["amount"]) if item.get("amount") is not None else None) for item in data.get("line_items", []))
    return InvoiceData(**data)
