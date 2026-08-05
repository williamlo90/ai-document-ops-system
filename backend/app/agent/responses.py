from __future__ import annotations

from dataclasses import replace
from typing import Callable
from uuid import UUID

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    get_tool_definition,
)
from app.agent.recommendations import recommend_next_action
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


class CopilotResponseFactory:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        extractions: ExtractionRepository,
        review_service: ReviewService,
        readiness: Callable[[], dict[str, bool]],
    ) -> None:
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.extractions = extractions
        self.review_service = review_service
        self.readiness = readiness

    def create(
        self,
        tool_name: AgentToolName,
        *,
        document_id: UUID | None,
        context: SecurityContext,
    ) -> AgentToolResponse | None:
        handlers = {
            AgentToolName.GET_READINESS: lambda: self._readiness_response(),
            AgentToolName.GET_METRICS_SUMMARY: lambda: self._metrics_response(context),
            AgentToolName.LIST_DOCUMENTS: lambda: self._list_documents_response(context),
            AgentToolName.LIST_REVIEW_QUEUE: lambda: self._review_queue_response(context),
            AgentToolName.GET_DOCUMENT_DETAIL: lambda: self._document_detail_response(
                document_id,
                context,
            ),
        }
        handler = handlers.get(tool_name)
        return handler() if handler is not None else None

    def add_recommendation(
        self,
        response: AgentToolResponse,
        context: SecurityContext,
    ) -> AgentToolResponse:
        data = dict(response.data)
        data["recommendation"] = recommend_next_action(response, context).to_dict()
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
        return AgentToolResponse(
            tool_name=AgentToolName.LIST_DOCUMENTS,
            status="success",
            risk=get_tool_definition(AgentToolName.LIST_DOCUMENTS).risk,
            summary=f"Found {len(documents)} document(s) in this workspace.",
            confidence=AgentConfidence.HIGH,
            evidence=(f"workspace_id={context.workspace_id}", f"documents={len(documents)}"),
            data={"documents": [document_response(document) for document in documents]},
        )

    def _review_queue_response(self, context: SecurityContext) -> AgentToolResponse:
        documents = self.review_service.list_queue(context)
        return AgentToolResponse(
            tool_name=AgentToolName.LIST_REVIEW_QUEUE,
            status="success",
            risk=get_tool_definition(AgentToolName.LIST_REVIEW_QUEUE).risk,
            summary=f"Review queue has {len(documents)} document(s).",
            confidence=AgentConfidence.HIGH,
            evidence=(f"workspace_id={context.workspace_id}", f"review_queue={len(documents)}"),
            data={"documents": [document_response(document) for document in documents]},
        )

    def _document_detail_response(
        self,
        document_id: UUID | None,
        context: SecurityContext,
    ) -> AgentToolResponse:
        definition = get_tool_definition(AgentToolName.GET_DOCUMENT_DETAIL)
        if document_id is None:
            return AgentToolResponse.escalated(
                tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
                risk=definition.risk,
                summary="A document id is required before the copilot can inspect details.",
            )
        try:
            document = self.documents.get(document_id)
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
        try:
            extraction = self.extractions.get_for_document(document.id)
        except NotFoundError:
            extraction = None
        audit_events = self.audits.list_for_document(document.id)
        validation_count = len(extraction.validation_report.issues) if extraction is not None else 0
        data = {
            "document": document_response(document),
            "extraction": extraction_response(extraction),
            "audit_events": [audit_response(event) for event in audit_events],
        }
        return AgentToolResponse(
            tool_name=AgentToolName.GET_DOCUMENT_DETAIL,
            status="success",
            risk=definition.risk,
            summary=(
                f"Document {document.original_filename} is {document.status.value} "
                f"with {validation_count} validation issue(s)."
            ),
            confidence=(
                AgentConfidence.HIGH if extraction or audit_events else AgentConfidence.MEDIUM
            ),
            evidence=(
                f"document_id={document.id}",
                f"status={document.status.value}",
                f"validation_issues={validation_count}",
            ),
            data=data,
        )
