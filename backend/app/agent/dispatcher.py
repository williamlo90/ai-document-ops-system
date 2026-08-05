from __future__ import annotations

from app.agent.contracts import AgentToolName, AgentToolResponse, get_tool_definition
from app.agent.responses import CopilotResponseFactory
from app.agent.tools import ControlledToolExecutor, ToolExecutionRequest
from app.agent.types import CopilotRequest
from app.core.security import SecurityContext


class CopilotToolDispatcher:
    def __init__(
        self,
        response_factory: CopilotResponseFactory,
        tool_executor: ControlledToolExecutor,
    ) -> None:
        self.response_factory = response_factory
        self.tool_executor = tool_executor

    def dispatch(
        self,
        request: CopilotRequest,
        context: SecurityContext,
        *,
        tool_name: AgentToolName,
    ) -> AgentToolResponse:
        response = self.response_factory.create(
            tool_name,
            document_id=request.document_id,
            context=context,
        )
        if response is not None:
            return response
        if request.execute_tool is not None:
            return self.tool_executor.execute(
                ToolExecutionRequest(
                    tool_name=request.execute_tool,
                    document_id=request.document_id,
                    confirmed=request.confirmed,
                ),
                context,
            )
        definition = get_tool_definition(tool_name)
        return AgentToolResponse.escalated(
            tool_name=tool_name,
            risk=definition.risk,
            summary="No read-only tool can safely answer this request yet.",
        )
