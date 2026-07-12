from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from app.core.security import SecurityContext


class AgentToolRisk(StrEnum):
    READ_ONLY = "read_only"
    OPERATOR_ACTION = "operator_action"
    REVIEW_ACTION = "review_action"
    ADMIN_ACTION = "admin_action"
    BLOCKED = "blocked"


class AgentConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentFailureType(StrEnum):
    WRONG_TOOL = "wrong_tool"
    MISSING_TOOL = "missing_tool"
    HALLUCINATED_STATE = "hallucinated_state"
    PERMISSION_DENIED = "permission_denied"
    WORKSPACE_BOUNDARY_VIOLATION = "workspace_boundary_violation"
    CONFIRMATION_REQUIRED = "confirmation_required"
    TIMEOUT = "timeout"
    INVALID_WORKFLOW_STATE = "invalid_workflow_state"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AgentToolName(StrEnum):
    GET_READINESS = "get_readiness"
    GET_METRICS_SUMMARY = "get_metrics_summary"
    LIST_DOCUMENTS = "list_documents"
    GET_DOCUMENT_DETAIL = "get_document_detail"
    LIST_REVIEW_QUEUE = "list_review_queue"
    PROCESS_DOCUMENT = "process_document"
    SAVE_REVIEW_NOTES = "save_review_notes"
    APPROVE_REVIEW = "approve_review"
    REJECT_REVIEW = "reject_review"
    EXPORT_APPROVED_CSV = "export_approved_csv"
    SEND_ACCOUNTING_INTEGRATION = "send_accounting_integration"


READ_ROLES = frozenset({"admin", "operator", "reviewer"})
REVIEW_ROLES = frozenset({"admin", "reviewer"})
ADMIN_ROLES = frozenset({"admin"})


@dataclass(frozen=True)
class AgentToolSchema:
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentToolDefinition:
    name: AgentToolName
    risk: AgentToolRisk
    purpose: str
    allowed_roles: frozenset[str]
    requires_confirmation: bool
    input_schema: AgentToolSchema = field(default_factory=AgentToolSchema)
    output_schema: AgentToolSchema = field(default_factory=AgentToolSchema)
    project2_capability: str = ""
    supports_human_escalation: bool = False
    confidence_behavior: str = "Return high confidence only when evidence is present."
    failure_types: frozenset[AgentFailureType] = field(default_factory=frozenset)

    def can_be_called_by(self, context: SecurityContext) -> bool:
        if context.role == "admin" and not context.is_admin:
            return False
        return context.role in self.allowed_roles


@dataclass(frozen=True)
class AgentToolResponse:
    tool_name: AgentToolName
    status: str
    risk: AgentToolRisk
    summary: str
    confidence: AgentConfidence
    evidence: tuple[str, ...] = ()
    data: Mapping[str, object] = field(default_factory=dict)
    requires_follow_up: bool = False
    error_code: str | None = None
    failure_type: AgentFailureType | None = None
    retryable: bool = False
    human_escalation_reason: str | None = None

    @classmethod
    def escalated(
        cls,
        *,
        tool_name: AgentToolName,
        risk: AgentToolRisk,
        summary: str,
    ) -> AgentToolResponse:
        return cls(
            tool_name=tool_name,
            status="escalated",
            risk=risk,
            summary=summary,
            confidence=AgentConfidence.LOW,
            requires_follow_up=True,
            failure_type=AgentFailureType.INSUFFICIENT_EVIDENCE,
            human_escalation_reason=summary,
        )


TOOL_DEFINITIONS: tuple[AgentToolDefinition, ...] = (
    AgentToolDefinition(
        name=AgentToolName.GET_READINESS,
        risk=AgentToolRisk.READ_ONLY,
        purpose="Check database and storage readiness.",
        allowed_roles=READ_ROLES,
        requires_confirmation=False,
        output_schema=AgentToolSchema(required=("status", "checks")),
        project2_capability="container.readiness and /ready",
        failure_types=frozenset({AgentFailureType.TOOL_EXECUTION_FAILED}),
    ),
    AgentToolDefinition(
        name=AgentToolName.GET_METRICS_SUMMARY,
        risk=AgentToolRisk.READ_ONLY,
        purpose="Summarize queue, provider, review, cost, and processing metrics.",
        allowed_roles=READ_ROLES,
        requires_confirmation=False,
        output_schema=AgentToolSchema(required=("documents_total", "queue", "provider", "review")),
        project2_capability="MetricsService.summary",
        failure_types=frozenset({AgentFailureType.TOOL_EXECUTION_FAILED}),
    ),
    AgentToolDefinition(
        name=AgentToolName.LIST_DOCUMENTS,
        risk=AgentToolRisk.READ_ONLY,
        purpose="List documents in the caller workspace.",
        allowed_roles=READ_ROLES,
        requires_confirmation=False,
        output_schema=AgentToolSchema(required=("documents",)),
        project2_capability="DocumentRepository.list_by_workspace",
        failure_types=frozenset({AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION}),
    ),
    AgentToolDefinition(
        name=AgentToolName.GET_DOCUMENT_DETAIL,
        risk=AgentToolRisk.READ_ONLY,
        purpose="Inspect one document, extraction, validation, and audit events.",
        allowed_roles=READ_ROLES,
        requires_confirmation=False,
        input_schema=AgentToolSchema(required=("document_id",)),
        output_schema=AgentToolSchema(
            required=("document",), optional=("extraction", "audit_events")
        ),
        project2_capability="Document detail API and repositories",
        supports_human_escalation=True,
        failure_types=frozenset(
            {
                AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION,
                AgentFailureType.MISSING_TOOL,
                AgentFailureType.INSUFFICIENT_EVIDENCE,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.LIST_REVIEW_QUEUE,
        risk=AgentToolRisk.READ_ONLY,
        purpose="List documents needing human review.",
        allowed_roles=REVIEW_ROLES,
        requires_confirmation=False,
        output_schema=AgentToolSchema(required=("documents",)),
        project2_capability="ReviewService.list_queue",
        supports_human_escalation=True,
        failure_types=frozenset(
            {
                AgentFailureType.PERMISSION_DENIED,
                AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.PROCESS_DOCUMENT,
        risk=AgentToolRisk.OPERATOR_ACTION,
        purpose="Process an uploaded or queued document through Project 2 processing.",
        allowed_roles=frozenset({"admin", "operator"}),
        requires_confirmation=True,
        input_schema=AgentToolSchema(required=("document_id",)),
        output_schema=AgentToolSchema(required=("document", "job")),
        project2_capability="DocumentProcessingService.process_document",
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.INVALID_WORKFLOW_STATE,
                AgentFailureType.PERMISSION_DENIED,
                AgentFailureType.WORKSPACE_BOUNDARY_VIOLATION,
                AgentFailureType.TOOL_EXECUTION_FAILED,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.SAVE_REVIEW_NOTES,
        risk=AgentToolRisk.REVIEW_ACTION,
        purpose="Save review notes or corrections through Project 2 review workflow.",
        allowed_roles=REVIEW_ROLES,
        requires_confirmation=True,
        input_schema=AgentToolSchema(
            required=("document_id",), optional=("notes", "corrected_data")
        ),
        output_schema=AgentToolSchema(required=("review_task",)),
        project2_capability="ReviewService.save_review",
        supports_human_escalation=True,
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.INVALID_WORKFLOW_STATE,
                AgentFailureType.PERMISSION_DENIED,
                AgentFailureType.INSUFFICIENT_EVIDENCE,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.APPROVE_REVIEW,
        risk=AgentToolRisk.REVIEW_ACTION,
        purpose="Approve a reviewable document through Project 2 review workflow.",
        allowed_roles=REVIEW_ROLES,
        requires_confirmation=True,
        input_schema=AgentToolSchema(required=("document_id",)),
        output_schema=AgentToolSchema(required=("review_task",)),
        project2_capability="ReviewService.approve",
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.INVALID_WORKFLOW_STATE,
                AgentFailureType.PERMISSION_DENIED,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.REJECT_REVIEW,
        risk=AgentToolRisk.REVIEW_ACTION,
        purpose="Reject a reviewable document through Project 2 review workflow.",
        allowed_roles=REVIEW_ROLES,
        requires_confirmation=True,
        input_schema=AgentToolSchema(required=("document_id",), optional=("notes",)),
        output_schema=AgentToolSchema(required=("review_task",)),
        project2_capability="ReviewService.reject",
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.INVALID_WORKFLOW_STATE,
                AgentFailureType.PERMISSION_DENIED,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.EXPORT_APPROVED_CSV,
        risk=AgentToolRisk.ADMIN_ACTION,
        purpose="Export approved invoices to CSV through Project 2 export workflow.",
        allowed_roles=ADMIN_ROLES,
        requires_confirmation=True,
        output_schema=AgentToolSchema(required=("csv_text",)),
        project2_capability="InvoiceExportService.export_approved_csv",
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.PERMISSION_DENIED,
                AgentFailureType.TOOL_EXECUTION_FAILED,
            }
        ),
    ),
    AgentToolDefinition(
        name=AgentToolName.SEND_ACCOUNTING_INTEGRATION,
        risk=AgentToolRisk.ADMIN_ACTION,
        purpose="Send an approved invoice to the mock accounting integration.",
        allowed_roles=ADMIN_ROLES,
        requires_confirmation=True,
        input_schema=AgentToolSchema(required=("document_id",)),
        output_schema=AgentToolSchema(required=("document", "integration")),
        project2_capability="InvoiceIntegrationService.send_approved_invoice",
        failure_types=frozenset(
            {
                AgentFailureType.CONFIRMATION_REQUIRED,
                AgentFailureType.INVALID_WORKFLOW_STATE,
                AgentFailureType.PERMISSION_DENIED,
                AgentFailureType.TOOL_EXECUTION_FAILED,
            }
        ),
    ),
)

TOOL_REGISTRY: Mapping[AgentToolName, AgentToolDefinition] = MappingProxyType(
    {tool.name: tool for tool in TOOL_DEFINITIONS}
)

BLOCKED_ACTIONS: Mapping[str, str] = MappingProxyType(
    {
        "edit_database_record": "Direct database mutation bypasses Project 2 services.",
        "change_workspace_id": "Workspace ownership must never be changed by the agent.",
        "change_user_role": "Role assignment is outside the copilot boundary.",
        "read_env_file": "Secrets must not be exposed to the agent.",
        "read_raw_storage_path": "Storage keys and local paths are implementation details.",
        "send_arbitrary_http_request": "Only explicit integration tools are allowed.",
        "approve_non_reviewable_document": "Approval must follow Project 2 workflow status rules.",
        "export_non_approved_document": "Only approved documents can be exported.",
        "invent_invoice_fields": "Invoice fields must come from extraction or review evidence.",
    }
)


def get_tool_definition(name: AgentToolName | str) -> AgentToolDefinition:
    return TOOL_REGISTRY[AgentToolName(name)]


def requires_confirmation(name: AgentToolName | str) -> bool:
    return get_tool_definition(name).requires_confirmation


def allowed_tools_for_context(context: SecurityContext) -> tuple[AgentToolDefinition, ...]:
    return tuple(tool for tool in TOOL_DEFINITIONS if tool.can_be_called_by(context))
