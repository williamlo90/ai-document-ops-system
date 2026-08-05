from __future__ import annotations

from copy import deepcopy
from uuid import UUID

from app.review.models import CorrectionEvent, ReviewRecord


class InMemoryReviewRepository:
    def __init__(self) -> None:
        self._records: dict[UUID, ReviewRecord] = {}

    def save(self, record: ReviewRecord) -> None:
        self._records[record.document_id] = deepcopy(record)

    def get(self, document_id: UUID) -> ReviewRecord | None:
        record = self._records.get(document_id)
        return deepcopy(record) if record is not None else None


class InMemoryCorrectionRepository:
    def __init__(self) -> None:
        self._events: list[CorrectionEvent] = []

    def append(self, event: CorrectionEvent) -> None:
        self._events.append(deepcopy(event))

    def list_for_document(self, document_id: UUID) -> list[CorrectionEvent]:
        return [deepcopy(event) for event in self._events if event.document_id == document_id]
