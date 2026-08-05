from __future__ import annotations

from dataclasses import dataclass

from app.agent.contracts import AgentToolName
from app.agent.types import CopilotRequest


@dataclass(frozen=True)
class RoutingRule:
    tool_name: AgentToolName
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CopilotRoute:
    tool_name: AgentToolName
    intent: str
    reason: str


ROUTING_RULES = (
    RoutingRule(
        AgentToolName.GET_READINESS,
        ("ready", "readiness", "health", "database", "storage"),
    ),
    RoutingRule(
        AgentToolName.LIST_REVIEW_QUEUE,
        ("review", "queue", "human"),
    ),
    RoutingRule(
        AgentToolName.GET_METRICS_SUMMARY,
        ("metric", "summary", "workflow", "status", "cost"),
    ),
    RoutingRule(
        AgentToolName.LIST_DOCUMENTS,
        ("document", "invoice", "list"),
    ),
)

MUTATION_KEYWORDS = (
    "approve",
    "reject",
    "process",
    "export",
    "send",
    "update",
    "delete",
    "change",
)

TOOL_INTENTS = {
    AgentToolName.GET_READINESS: "inspect_readiness",
    AgentToolName.GET_METRICS_SUMMARY: "summarize_workflow",
    AgentToolName.LIST_DOCUMENTS: "list_documents",
    AgentToolName.GET_DOCUMENT_DETAIL: "explain_document",
    AgentToolName.LIST_REVIEW_QUEUE: "summarize_review_queue",
}


class CopilotIntentRouter:
    def route(self, request: CopilotRequest) -> CopilotRoute:
        tool_name = self._select_tool(request)
        intent = (
            "execute_controlled_tool"
            if request.execute_tool is not None
            else TOOL_INTENTS.get(tool_name, "unsupported")
        )
        return CopilotRoute(
            tool_name=tool_name,
            intent=intent,
            reason=f"Selected {tool_name.value} from deterministic read-only routing.",
        )

    def is_mutation_request(self, message: str) -> bool:
        text = message.lower()
        return any(keyword in text for keyword in MUTATION_KEYWORDS)

    def _select_tool(self, request: CopilotRequest) -> AgentToolName:
        if request.execute_tool is not None:
            return request.execute_tool
        if request.document_id is not None:
            return AgentToolName.GET_DOCUMENT_DETAIL
        text = request.message.lower()
        for rule in ROUTING_RULES:
            if any(keyword in text for keyword in rule.keywords):
                return rule.tool_name
        return AgentToolName.GET_METRICS_SUMMARY
