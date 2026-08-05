from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.review.models import CorrectionEvent, ReviewRecord


@runtime_checkable
class ReviewRepositoryPort(Protocol):
    def save(self, record: ReviewRecord) -> None: ...

    def get(self, document_id: UUID) -> ReviewRecord | None: ...


@runtime_checkable
class CorrectionRepositoryPort(Protocol):
    def append(self, event: CorrectionEvent) -> None: ...

    def list_for_document(self, document_id: UUID) -> list[CorrectionEvent]: ...
