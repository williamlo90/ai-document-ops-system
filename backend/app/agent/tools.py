from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.agent.contracts import (
    AgentConfidence,
    AgentFailureType,
    AgentToolName,
    AgentToolResponse,
    get_tool_definition,
)
from app.api.serializers import document_response, job_response
from app.core.security import SecurityContext, UnauthorizedError
from app.documents.repositories import NotFoundError
from app.documents.services import DocumentProcessingService
from app.documents.status import InvalidStatusTransition
from app.exports.services import InvoiceExportService
from app.integrations.models import IntegrationDeliveryError
from app.integrations.services import InvoiceIntegrationService


@dataclass(frozen=True)
class ToolExecutionRequest:
    tool_name: AgentToolName
    document_id: UUID | None = None
    confirmed: bool = False


class ControlledToolExecutor:
    def __init__(
        self,
        *,
        processing_service: DocumentProcessingService,
        export_service: InvoiceExportService,
        integration_service: InvoiceIntegrationService,
    ) -> None:
        self.processing_service = processing_service
        self.export_service = export_service
        self.integration_service = integration_service

    def execute(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        definition = get_tool_definition(request.tool_name)
        if not definition.can_be_called_by(context):
            return AgentToolResponse(
                tool_name=request.tool_name,
                status="escalated",
                risk=definition.risk,
                summary="The current role cannot execute this tool.",
                confidence=AgentConfidence.LOW,
                requires_follow_up=True,
                failure_type=AgentFailureType.PERMISSION_DENIED,
                human_escalation_reason="Ask an authorized operator or admin to execute it.",
            )
        if definition.requires_confirmation and not request.confirmed:
            return AgentToolResponse(
                tool_name=request.tool_name,
                status="confirmation_required",
                risk=definition.risk,
                summary="This tool requires explicit confirmation before execution.",
                confidence=AgentConfidence.MEDIUM,
                requires_follow_up=True,
                failure_type=AgentFailureType.CONFIRMATION_REQUIRED,
                human_escalation_reason="Confirm the action before running the tool.",
            )
        if request.tool_name == AgentToolName.PROCESS_DOCUMENT:
            return self._process_document(request, context)
        if request.tool_name == AgentToolName.EXPORT_APPROVED_CSV:
            return self._export_approved_csv(context)
        if request.tool_name == AgentToolName.SEND_ACCOUNTING_INTEGRATION:
            return self._send_accounting_integration(request, context)
        return AgentToolResponse(
            tool_name=request.tool_name,
            status="escalated",
            risk=definition.risk,
            summary="This tool is defined but not enabled for controlled execution yet.",
            confidence=AgentConfidence.LOW,
            requires_follow_up=True,
            failure_type=AgentFailureType.MISSING_TOOL,
            human_escalation_reason="Use the protected document workflow for this action.",
        )

    def _process_document(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        definition = get_tool_definition(AgentToolName.PROCESS_DOCUMENT)
        if request.document_id is None:
            return _missing_document_id(AgentToolName.PROCESS_DOCUMENT)
        try:
            document = self.processing_service.process_document(request.document_id, context)
            job = self.processing_service.jobs.get_latest_for_document(document.id)
        except UnauthorizedError:
            return _permission_denied(AgentToolName.PROCESS_DOCUMENT)
        except NotFoundError:
            return _not_found(AgentToolName.PROCESS_DOCUMENT)
        except InvalidStatusTransition as exc:
            return _invalid_workflow(AgentToolName.PROCESS_DOCUMENT, str(exc))
        return AgentToolResponse(
            tool_name=AgentToolName.PROCESS_DOCUMENT,
            status="success",
            risk=definition.risk,
            summary=f"Processed document {document.id}; status is now {document.status.value}.",
            confidence=AgentConfidence.HIGH,
            evidence=(f"document_id={document.id}", f"status={document.status.value}"),
            data={"document": document_response(document), "job": job_response(job)},
        )

    def _export_approved_csv(self, context: SecurityContext) -> AgentToolResponse:
        definition = get_tool_definition(AgentToolName.EXPORT_APPROVED_CSV)
        try:
            csv_text = self.export_service.export_approved_csv(context=context)
        except UnauthorizedError:
            return _permission_denied(AgentToolName.EXPORT_APPROVED_CSV)
        except NotFoundError:
            return _not_found(AgentToolName.EXPORT_APPROVED_CSV)
        lines = [line for line in csv_text.splitlines() if line.strip()]
        exported_rows = max(len(lines) - 1, 0)
        return AgentToolResponse(
            tool_name=AgentToolName.EXPORT_APPROVED_CSV,
            status="success",
            risk=definition.risk,
            summary=f"Exported {exported_rows} approved invoice row(s) to CSV.",
            confidence=AgentConfidence.HIGH,
            evidence=(f"exported_rows={exported_rows}",),
            data={"exported_rows": exported_rows, "csv_text": csv_text},
        )

    def _send_accounting_integration(
        self,
        request: ToolExecutionRequest,
        context: SecurityContext,
    ) -> AgentToolResponse:
        definition = get_tool_definition(AgentToolName.SEND_ACCOUNTING_INTEGRATION)
        if request.document_id is None:
            return _missing_document_id(AgentToolName.SEND_ACCOUNTING_INTEGRATION)
        try:
            result = self.integration_service.send_approved_invoice(request.document_id, context)
        except UnauthorizedError:
            return _permission_denied(AgentToolName.SEND_ACCOUNTING_INTEGRATION)
        except NotFoundError:
            return _not_found(AgentToolName.SEND_ACCOUNTING_INTEGRATION)
        except InvalidStatusTransition as exc:
            return _invalid_workflow(AgentToolName.SEND_ACCOUNTING_INTEGRATION, str(exc))
        except IntegrationDeliveryError as exc:
            return AgentToolResponse(
                tool_name=AgentToolName.SEND_ACCOUNTING_INTEGRATION,
                status="failed",
                risk=definition.risk,
                summary="Integration delivery failed.",
                confidence=AgentConfidence.LOW,
                error_code=exc.code,
                failure_type=AgentFailureType.TOOL_EXECUTION_FAILED,
                retryable=exc.retryable,
                human_escalation_reason=(
                    "Retry later if retryable, otherwise inspect integration configuration."
                ),
            )
        return AgentToolResponse(
            tool_name=AgentToolName.SEND_ACCOUNTING_INTEGRATION,
            status="success",
            risk=definition.risk,
            summary=(
                "Sent approved invoice to accounting integration; "
                f"status is {result.integration_result.status}."
            ),
            confidence=AgentConfidence.HIGH,
            evidence=(
                f"document_id={result.document.id}",
                f"external_id={result.integration_result.external_id}",
            ),
            data={
                "document": document_response(result.document),
                "integration": {
                    "adapter_name": result.integration_result.adapter_name,
                    "external_id": result.integration_result.external_id,
                    "status": result.integration_result.status,
                    "retryable": result.integration_result.retryable,
                },
            },
        )


def _missing_document_id(tool_name: AgentToolName) -> AgentToolResponse:
    definition = get_tool_definition(tool_name)
    return AgentToolResponse.escalated(
        tool_name=tool_name,
        risk=definition.risk,
        summary="A document id is required before this tool can run.",
    )


def _not_found(tool_name: AgentToolName) -> AgentToolResponse:
    definition = get_tool_definition(tool_name)
    return AgentToolResponse(
        tool_name=tool_name,
        status="escalated",
        risk=definition.risk,
        summary="The requested document is unavailable in this workspace.",
        confidence=AgentConfidence.LOW,
        requires_follow_up=True,
        failure_type=AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION,
        human_escalation_reason="The tool cannot use evidence from another workspace.",
    )


def _permission_denied(tool_name: AgentToolName) -> AgentToolResponse:
    definition = get_tool_definition(tool_name)
    return AgentToolResponse(
        tool_name=tool_name,
        status="escalated",
        risk=definition.risk,
        summary="The document workflow denied this tool for the current role.",
        confidence=AgentConfidence.LOW,
        requires_follow_up=True,
        failure_type=AgentFailureType.PERMISSION_DENIED,
        human_escalation_reason="Ask an authorized admin to execute this action.",
    )


def _invalid_workflow(tool_name: AgentToolName, message: str) -> AgentToolResponse:
    definition = get_tool_definition(tool_name)
    return AgentToolResponse(
        tool_name=tool_name,
        status="failed",
        risk=definition.risk,
        summary=message,
        confidence=AgentConfidence.LOW,
        requires_follow_up=True,
        failure_type=AgentFailureType.INVALID_WORKFLOW_STATE,
        human_escalation_reason="Use a valid workflow transition before retrying this tool.",
    )
