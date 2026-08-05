from __future__ import annotations

from typing import Callable

from app.agent.contracts import (
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    get_tool_definition,
)
from app.agent.dispatcher import CopilotToolDispatcher
from app.agent.repositories import AgentRunRepository
from app.agent.responses import CopilotResponseFactory
from app.agent.routing import CopilotIntentRouter
from app.agent.run_recorder import CopilotRunRecorder
from app.agent.tools import ControlledToolExecutor
from app.agent.types import CopilotRequest, CopilotResult
from app.core.security import SecurityContext
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
)
from app.review.services import ReviewService

__all__ = ["CopilotRequest", "CopilotResult", "ReadOnlyCopilotService"]


class ReadOnlyCopilotService:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        extractions: ExtractionRepository,
        review_service: ReviewService,
        agent_runs: AgentRunRepository,
        tool_executor: ControlledToolExecutor,
        readiness: Callable[[], dict[str, bool]],
    ) -> None:
        self.router = CopilotIntentRouter()
        self.response_factory = CopilotResponseFactory(
            documents=documents,
            jobs=jobs,
            audits=audits,
            extractions=extractions,
            review_service=review_service,
            readiness=readiness,
        )
        self.dispatcher = CopilotToolDispatcher(self.response_factory, tool_executor)
        self.run_recorder = CopilotRunRecorder(agent_runs)

    def answer(self, request: CopilotRequest, context: SecurityContext) -> CopilotResult:
        route = self.router.route(request)
        definition = get_tool_definition(route.tool_name)
        run = self.run_recorder.start(request, context, route)
        if definition.can_be_called_by(context):
            response = self.dispatcher.dispatch(
                request,
                context,
                tool_name=route.tool_name,
            )
            run.confidence = response.confidence
            run.human_escalation_reason = response.human_escalation_reason
            run.failure_type = response.failure_type
        else:
            response = self._permission_denied_response(route.tool_name)
            run.human_escalation_reason = response.human_escalation_reason
            run.failure_type = AgentFailureType.PERMISSION_DENIED
        response = self.response_factory.add_recommendation(response, context)
        self.run_recorder.finish(
            run,
            response,
            request,
            mutation_requested=self.router.is_mutation_request(request.message),
        )
        return CopilotResult(run=run, tool_response=response)

    def _permission_denied_response(
        self,
        tool_name: AgentToolName,
    ) -> AgentToolResponse:
        definition = get_tool_definition(tool_name)
        return AgentToolResponse.escalated(
            tool_name=tool_name,
            risk=definition.risk,
            summary="The copilot cannot inspect this area with the current role.",
        )
