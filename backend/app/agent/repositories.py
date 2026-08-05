from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.agent.models import AssistantAnswer


@dataclass(frozen=True, slots=True)
class AgentRun:
    document_id: UUID
    question: str
    answer: AssistantAnswer
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AgentRunRepository:
    def __init__(self) -> None:
        self._runs: list[AgentRun] = []

    def append(self, run: AgentRun) -> None:
        self._runs.append(run)

    def list_for_document(self, document_id: UUID) -> list[AgentRun]:
        return [run for run in self._runs if run.document_id == document_id]
