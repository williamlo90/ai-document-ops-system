from __future__ import annotations

from uuid import UUID

from app.agent.models import AssistantAnswer
from app.agent.repositories import AgentRun, AgentRunRepository
from app.agent.tools import ReadOnlyInvoiceTools


class ReadOnlyCopilotService:
    def __init__(self, tools: ReadOnlyInvoiceTools, runs: AgentRunRepository) -> None:
        self.tools = tools
        self.runs = runs

    def answer(self, document_id: UUID, question: str) -> AssistantAnswer:
        requested = "total" if "total" in question.casefold() else "vendor_name" if "vendor" in question.casefold() else None
        citation = self.tools.field(document_id, requested) if requested else None
        answer = AssistantAnswer("I do not have grounded evidence for that question.", (), True) if citation is None else AssistantAnswer(f"{citation.field_name}: {citation.value}", (citation,))
        self.runs.append(AgentRun(document_id, question, answer))
        return answer
