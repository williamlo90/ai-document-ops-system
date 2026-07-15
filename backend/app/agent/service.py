from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from uuid import UUID

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    get_tool_definition,
)
from app.agent.models import AgentRun, AgentToolCallTrace
from app.agent.recommendations import recommend_next_action
from app.agent.repositories import AgentRunRepository
from app.agent.tools import ControlledToolExecutor, ToolExecutionRequest
from app.api.serializers import audit_response, document_response, extraction_response
from app.core.observability import readiness_payload
from app.core.security import SecurityContext
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
    NotFoundError,
)
from app.metrics.services import ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD
from app.review.services import ReviewService


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
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.extractions = extractions
        self.review_service = review_service
        self.agent_runs = agent_runs
        self.tool_executor = tool_executor
        self.readiness = readiness

    def answer(self, request: CopilotRequest, context: SecurityContext) -> CopilotResult:
        tool_name = self._select_tool(request)
        tool_definition = get_tool_definition(tool_name)
        run = AgentRun(
            workspace_id=context.workspace_id,
            actor=context.actor,
            request=request.message,
            intent=self._intent_for_tool(tool_name, executing=request.execute_tool is not None),
            expected_tool=request.expected_tool,
            selected_tool=tool_name,
            selection_reason=self._selection_reason(tool_name),
        )
        if not tool_definition.can_be_called_by(context):
            response = AgentToolResponse.escalated(
                tool_name=tool_name,
                risk=tool_definition.risk,
                summary="The copilot cannot inspect this area with the current role.",
            )
            run.human_escalation_reason = response.human_escalation_reason
            run.failure_type = AgentFailureType.PERMISSION_DENIED
        else:
            response = self._execute_tool(tool_name, request, context)
            run.confidence = response.confidence
            run.human_escalation_reason = response.human_escalation_reason
            run.failure_type = response.failure_type
        response = self._with_recommendation(response, context)
        trace = AgentToolCallTrace(
            tool_name=response.tool_name,
            risk=response.risk,
            status=response.status,
            summary=response.summary,
            confidence=response.confidence,
            evidence=response.evidence,
            input_summary=self._input_summary(request),
            output_summary=response.summary,
            error_code=response.error_code,
            failure_type=response.failure_type,
            retryable=response.retryable,
            human_escalation_reason=response.human_escalation_reason,
        )
        run.add_tool_call(trace)
        if self._is_mutation_request(request.message) and request.execute_tool is None:
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
        return CopilotResult(run=run, tool_response=response)

    def _execute_tool(
        self,
        tool_name: AgentToolName,
        request: CopilotRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        if tool_name == AgentToolName.GET_READINESS:
            return self._readiness_response()
        if tool_name == AgentToolName.GET_METRICS_SUMMARY:
            return self._metrics_response(context)
        if tool_name == AgentToolName.LIST_DOCUMENTS:
            return self._list_documents_response(context)
        if tool_name == AgentToolName.LIST_REVIEW_QUEUE:
            return self._review_queue_response(context)
        if tool_name == AgentToolName.GET_DOCUMENT_DETAIL:
            return self._document_detail_response(request, context)
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

    def _with_recommendation(
        self,
        response: AgentToolResponse,
        context: SecurityContext,
    ) -> AgentToolResponse:
        recommendation = recommend_next_action(response, context)
        data = dict(response.data)
        data["recommendation"] = recommendation.to_dict()
        return replace(response, data=data)

    def _readiness_response(self) -> AgentToolResponse:
        checks = self.readiness()
        data = readiness_payload(
            database_ready=checks["database"],
            storage_ready=checks["storage"],
        )
        return AgentToolResponse(
            tool_name=AgentToolName.GET_READINESS,
            status="success",
            risk=get_tool_definition(AgentToolName.GET_READINESS).risk,
            summary=f"System readiness is {data['status']}.",
            confidence=AgentConfidence.HIGH,
            evidence=(
                f"database={data['checks']['database']}",
                f"storage={data['checks']['storage']}",
            ),
            data=data,
        )

    def _metrics_response(self, context: SecurityContext) -> AgentToolResponse:
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_ids = {document.id for document in documents}
        jobs = [job for job in self.jobs.list_all() if job.document_id in document_ids]
        audit_events = [
            event
            for document_id in document_ids
            for event in self.audits.list_for_document(document_id)
        ]
        by_status: dict[str, int] = {}
        for document in documents:
            by_status[document.status.value] = by_status.get(document.status.value, 0) + 1
        succeeded_jobs = [job for job in jobs if job.status.value == "succeeded"]
        review_count = by_status.get("needs_review", 0)
        data = {
            "documents_total": len(documents),
            "jobs_total": len(jobs),
            "audit_events_total": len(audit_events),
            "by_status": by_status,
            "review_queue_count": review_count,
            "estimated_cost_usd": round(
                len(succeeded_jobs) * ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD,
                6,
            ),
        }
        summary = (
            f"Workspace has {len(documents)} document(s), "
            f"{len(jobs)} job(s), and {review_count} item(s) needing review."
        )
        return AgentToolResponse(
            tool_name=AgentToolName.GET_METRICS_SUMMARY,
            status="success",
            risk=get_tool_definition(AgentToolName.GET_METRICS_SUMMARY).risk,
            summary=summary,
            confidence=AgentConfidence.HIGH,
            evidence=(
                f"documents_total={len(documents)}",
                f"jobs_total={len(jobs)}",
                f"review_queue_count={review_count}",
            ),
            data=data,
        )

    def _list_documents_response(self, context: SecurityContext) -> AgentToolResponse:
        documents = self.documents.list_by_workspace(context.workspace_id)
        data = {"documents": [document_response(document) for document in documents]}
        return AgentToolResponse(
            tool_name=AgentToolName.LIST_DOCUMENTS,
            status="success",
            risk=get_tool_definition(AgentToolName.LIST_DOCUMENTS).risk,
            summary=f"Found {len(documents)} document(s) in this workspace.",
            confidence=AgentConfidence.HIGH,
            evidence=(f"workspace_id={context.workspace_id}", f"documents={len(documents)}"),
            data=data,
        )

    def _review_queue_response(self, context: SecurityContext) -> AgentToolResponse:
        documents = self.review_service.list_queue(context)
        data = {"documents": [document_response(document) for document in documents]}
        return AgentToolResponse(
            tool_name=AgentToolName.LIST_REVIEW_QUEUE,
            status="success",
            risk=get_tool_definition(AgentToolName.LIST_REVIEW_QUEUE).risk,
            summary=f"Review queue has {len(documents)} document(s).",
            confidence=AgentConfidence.HIGH,
            evidence=(f"workspace_id={context.workspace_id}", f"review_queue={len(documents)}"),
            data=data,
        )

    def _document_detail_response(
        self,
        request: CopilotRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        definition = get_tool_definition(AgentToolName.GET_DOCUMENT_DETAIL)
        if request.document_id is None:
            return AgentToolResponse.escalated(
                tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
                risk=definition.risk,
                summary="A document id is required before the copilot can inspect details.",
            )
        try:
            document = self.documents.get(request.document_id)
        except NotFoundError:
            return AgentToolResponse.escalated(
                tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
                risk=definition.risk,
                summary="The requested document is unavailable in this workspace.",
            )
        if document.workspace_id != context.workspace_id:
            return AgentToolResponse(
                tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
                status="escalated",
                risk=definition.risk,
                summary="The requested document is unavailable in this workspace.",
                confidence=AgentConfidence.LOW,
                requires_follow_up=True,
                failure_type=AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION,
                human_escalation_reason=("The copilot cannot use evidence from another workspace."),
            )
        extraction = None
        try:
            extraction = self.extractions.get_for_document(document.id)
        except NotFoundError:
            pass
        audit_events = self.audits.list_for_document(document.id)
        validation_count = 0
        if extraction is not None:
            validation_count = len(extraction.validation_report.issues)
        data = {
            "document": document_response(document),
            "extraction": extraction_response(extraction),
            "audit_events": [audit_response(event) for event in audit_events],
        }
        summary = (
            f"Document {document.original_filename} is {document.status.value} "
            f"with {validation_count} validation issue(s)."
        )
        confidence = AgentConfidence.HIGH if extraction or audit_events else AgentConfidence.MEDIUM
        return AgentToolResponse(
            tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
            status="success",
            risk=definition.risk,
            summary=summary,
            confidence=confidence,
            evidence=(
                f"document_id={document.id}",
                f"status={document.status.value}",
                f"validation_issues={validation_count}",
            ),
            data=data,
        )

    def _select_tool(self, request: CopilotRequest) -> AgentToolName:
        if request.execute_tool is not None:
            return request.execute_tool
        text = request.message.lower()
        if request.document_id is not None:
            return AgentToolName.GET_DOCUMENT_DETAIL
        if any(word in text for word in ("ready", "readiness", "health", "database", "storage")):
            return AgentToolName.GET_READINESS
        if any(word in text for word in ("review", "queue", "human")):
            return AgentToolName.LIST_REVIEW_QUEUE
        if any(word in text for word in ("metric", "summary", "workflow", "status", "cost")):
            return AgentToolName.GET_METRICS_SUMMARY
        if any(word in text for word in ("document", "invoice", "list")):
            return AgentToolName.LIST_DOCUMENTS
        return AgentToolName.GET_METRICS_SUMMARY

    def _intent_for_tool(self, tool_name: AgentToolName, *, executing: bool = False) -> str:
        if executing:
            return "execute_controlled_tool"
        return {
            AgentToolName.GET_READINESS: "inspect_readiness",
            AgentToolName.GET_METRICS_SUMMARY: "summarize_workflow",
            AgentToolName.LIST_DOCUMENTS: "list_documents",
            AgentToolName.GET_DOCUMENT_DETAIL: "explain_document",
            AgentToolName.LIST_REVIEW_QUEUE: "summarize_review_queue",
        }.get(tool_name, "unsupported")

    def _selection_reason(self, tool_name: AgentToolName) -> str:
        return f"Selected {tool_name.value} from deterministic read-only routing."

    def _input_summary(self, request: CopilotRequest) -> str:
        if request.document_id is None:
            return request.message
        return f"{request.message}; document_id={request.document_id}"

    def _why_not(self, response: AgentToolResponse) -> str | None:
        if response.status == "success":
            if response.risk.value == "read_only":
                return "No mutation tool was used for this read-only request."
            return "Controlled execution used an explicit tool with service guardrails."
        if response.human_escalation_reason:
            return response.human_escalation_reason
        return None

    def _is_mutation_request(self, message: str) -> bool:
        text = message.lower()
        return any(
            word in text
            for word in (
                "approve",
                "reject",
                "process",
                "export",
                "send",
                "update",
                "delete",
                "change",
            )
        )
