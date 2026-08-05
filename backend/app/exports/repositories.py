from __future__ import annotations

from copy import deepcopy
from threading import RLock
from uuid import UUID

from app.exports.models import ExportRecord


class ExportAlreadyCompleted(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


class InMemoryExportRepository:
    def __init__(self) -> None:
        self._by_idempotency_key: dict[str, ExportRecord] = {}
        self._by_document: dict[UUID, ExportRecord] = {}
        self._lock = RLock()

    def get_by_idempotency_key(self, key: str) -> ExportRecord | None:
        with self._lock:
            record = self._by_idempotency_key.get(key)
            return deepcopy(record) if record is not None else None

    def record_success(self, record: ExportRecord) -> ExportRecord:
        with self._lock:
            existing_for_key = self._by_idempotency_key.get(record.idempotency_key)
            if existing_for_key is not None:
                if existing_for_key.document_id != record.document_id:
                    raise IdempotencyConflict(
                        "Idempotency key is already associated with another invoice"
                    )
                return deepcopy(existing_for_key)

            existing_for_document = self._by_document.get(record.document_id)
            if existing_for_document is not None:
                raise ExportAlreadyCompleted("Invoice already has a successful export")

            stored = deepcopy(record)
            self._by_idempotency_key[record.idempotency_key] = stored
            self._by_document[record.document_id] = stored
            return deepcopy(stored)

    def list_for_document(self, document_id: UUID) -> tuple[ExportRecord, ...]:
        with self._lock:
            record = self._by_document.get(document_id)
            return (deepcopy(record),) if record is not None else ()

