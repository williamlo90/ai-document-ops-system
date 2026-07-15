from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.review.models import CorrectionEvent


class CorrectionEventRepository(Protocol):
    def add(self, event: CorrectionEvent) -> CorrectionEvent: ...

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[CorrectionEvent]: ...

    def list_by_workspace(self, workspace_id: str) -> list[CorrectionEvent]: ...


@dataclass
class InMemoryCorrectionEventRepository:
    records: list[CorrectionEvent] = field(default_factory=list)

    def add(self, event: CorrectionEvent) -> CorrectionEvent:
        self.records.append(event)
        return event

    def list_for_document(self, workspace_id: str, document_id: UUID) -> list[CorrectionEvent]:
        return sorted(
            (
                event
                for event in self.records
                if event.workspace_id == workspace_id and event.document_id == document_id
            ),
            key=lambda event: event.created_at,
        )

    def list_by_workspace(self, workspace_id: str) -> list[CorrectionEvent]:
        return sorted(
            (event for event in self.records if event.workspace_id == workspace_id),
            key=lambda event: event.created_at,
        )
