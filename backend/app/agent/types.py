from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.agent.contracts import AgentToolName, AgentToolResponse
from app.agent.models import AgentRun


@dataclass(frozen=True)
class CopilotRequest:
    message: str
    document_id: UUID | None = None
    expected_tool: AgentToolName | None = None
    execute_tool: AgentToolName | None = None
    confirmed: bool = False


@dataclass(frozen=True)
class CopilotResult:
    run: AgentRun
    tool_response: AgentToolResponse
