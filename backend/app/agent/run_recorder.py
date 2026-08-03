from __future__ import annotations

from app.agent.contracts import AgentToolResponse
from app.agent.models import AgentRun, AgentToolCallTrace
from app.agent.repositories import AgentRunRepository
from app.agent.routing import CopilotRoute
from app.agent.types import CopilotRequest
from app.core.security import SecurityContext


class CopilotRunRecorder:
    def __init__(self, agent_runs: AgentRunRepository) -> None:
        self.agent_runs = agent_runs

    def start(
        self,
        request: CopilotRequest,
        context: SecurityContext,
        route: CopilotRoute,
    ) -> AgentRun:
        return AgentRun(
            workspace_id=context.workspace_id,
            actor=context.actor,
            request=request.message,
            intent=route.intent,
            expected_tool=request.expected_tool,
            selected_tool=route.tool_name,
            selection_reason=route.reason,
        )

    def finish(
        self,
        run: AgentRun,
        response: AgentToolResponse,
        request: CopilotRequest,
        *,
        mutation_requested: bool,
    ) -> None:
        run.add_tool_call(self._trace(response, request))
        if mutation_requested and request.execute_tool is None:
            reason = (
                "Read-only copilot blocked direct execution; Step 5 recommends actions "
                "but does not execute them."
            )
            run.block_action(reason)
            run.why_not = reason
        else:
            run.why_not = self._why_not(response)
        run.complete(response.summary)
        self.agent_runs.add(run)

    def _trace(
        self,
        response: AgentToolResponse,
        request: CopilotRequest,
    ) -> AgentToolCallTrace:
        input_summary = request.message
        if request.document_id is not None:
            input_summary = f"{request.message}; document_id={request.document_id}"
        return AgentToolCallTrace(
            tool_name=response.tool_name,
            risk=response.risk,
            status=response.status,
            summary=response.summary,
            confidence=response.confidence,
            evidence=response.evidence,
            input_summary=input_summary,
            output_summary=response.summary,
            error_code=response.error_code,
            failure_type=response.failure_type,
            retryable=response.retryable,
            human_escalation_reason=response.human_escalation_reason,
        )

    def _why_not(self, response: AgentToolResponse) -> str | None:
        if response.status == "success":
            if response.risk.value == "read_only":
                return "No mutation tool was used for this read-only request."
            return "Controlled execution used an explicit tool with service guardrails."
        return response.human_escalation_reason
