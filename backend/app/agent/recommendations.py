from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.agent.contracts import (
    AgentConfidence,
    AgentToolName,
    AgentToolResponse,
    AgentToolRisk,
    get_tool_definition,
)
from app.core.security import SecurityContext


@dataclass(frozen=True)
class ActionRecommendation:
    action: str
    recommended_tool: AgentToolName | None
    risk: AgentToolRisk
    confidence: AgentConfidence
    evidence: tuple[str, ...]
    why: str
    why_not: tuple[str, ...]
    requires_confirmation: bool = False
    requires_human: bool = False
    human_escalation_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "recommended_tool": self.recommended_tool.value if self.recommended_tool else None,
            "risk": self.risk.value,
            "confidence": self.confidence.value,
            "evidence": list(self.evidence),
            "why": self.why,
            "why_not": list(self.why_not),
            "requires_confirmation": self.requires_confirmation,
            "requires_human": self.requires_human,
            "human_escalation_reason": self.human_escalation_reason,
        }


def recommend_next_action(
    response: AgentToolResponse,
    context: SecurityContext,
) -> ActionRecommendation:
    if response.status != "success":
        return _human_escalation(
            evidence=response.evidence,
            reason=response.human_escalation_reason or response.summary,
        )
    if response.tool_name == AgentToolName.GET_DOCUMENT_DETAIL:
        return _recommend_for_document(response.data, context)
    if response.tool_name == AgentToolName.GET_METRICS_SUMMARY:
        return _recommend_for_metrics(response.data, context)
    if response.tool_name == AgentToolName.LIST_REVIEW_QUEUE:
        return _recommend_for_review_queue(response.data, context)
    if response.tool_name == AgentToolName.GET_READINESS:
        return _recommend_for_readiness(response.data)
    if response.tool_name == AgentToolName.LIST_DOCUMENTS:
        return _recommend_for_document_list(response.data)
    return _human_escalation(
        evidence=response.evidence,
        reason="No recommendation rule exists for this tool response yet.",
    )


def _recommend_for_document(
    data: Mapping[str, object],
    context: SecurityContext,
) -> ActionRecommendation:
    document = data.get("document")
    if not isinstance(document, Mapping):
        return _human_escalation(evidence=(), reason="Document evidence is missing.")
    status = str(document.get("status") or "")
    document_id = str(document.get("id") or "")
    filename = str(document.get("original_filename") or "document")
    evidence = (f"document_id={document_id}", f"status={status}")
    if status in {"uploaded", "queued"}:
        return _tool_recommendation(
            tool_name=AgentToolName.PROCESS_DOCUMENT,
            context=context,
            action=f"Process {filename}",
            evidence=evidence,
            why="The document is not processed yet, so extraction should happen before review or export.",
            why_not=(
                "Do not approve before extraction and validation exist.",
                "Do not export because only approved documents can be exported.",
            ),
        )
    if status == "needs_review":
        return _tool_recommendation(
            tool_name=AgentToolName.SAVE_REVIEW_NOTES,
            context=context,
            action=f"Send {filename} to human review",
            evidence=evidence + _validation_evidence(data),
            why="The workflow explicitly marked this document as needing review.",
            why_not=(
                "Do not export until review approval is complete.",
                "Do not auto-approve while validation or reviewer evidence is unresolved.",
            ),
            requires_human=True,
            human_escalation_reason="A reviewer should inspect and correct this document.",
        )
    if status == "approved":
        return _tool_recommendation(
            tool_name=AgentToolName.EXPORT_APPROVED_CSV,
            context=context,
            action=f"Prepare export for {filename}",
            evidence=evidence,
            why="The document is approved, so export is the next workflow step.",
            why_not=(
                "Do not approve again because the document is already approved.",
                "Do not reprocess unless an operator has evidence that extraction is stale.",
            ),
        )
    if status == "extracted":
        return _tool_recommendation(
            tool_name=AgentToolName.APPROVE_REVIEW,
            context=context,
            action=f"Review extracted fields for {filename}",
            evidence=evidence + _validation_evidence(data),
            why="Extraction exists, but the document is not approved or exported yet.",
            why_not=(
                "Do not export before approval.",
                "Do not send to accounting before an approved export state exists.",
            ),
            requires_human=True,
            human_escalation_reason="A reviewer should confirm extracted fields before approval.",
        )
    if status in {"exported", "rejected", "failed"}:
        return _human_escalation(
            evidence=evidence,
            reason=f"The document is in terminal or exceptional state: {status}.",
        )
    return _human_escalation(
        evidence=evidence,
        reason="The document status is not recognized by the recommendation rules.",
    )


def _recommend_for_metrics(
    data: Mapping[str, object],
    context: SecurityContext,
) -> ActionRecommendation:
    review_count = int(data.get("review_queue_count") or 0)
    documents_total = int(data.get("documents_total") or 0)
    evidence = (f"documents_total={documents_total}", f"review_queue_count={review_count}")
    if review_count > 0:
        return _tool_recommendation(
            tool_name=AgentToolName.LIST_REVIEW_QUEUE,
            context=context,
            action="Inspect review queue",
            evidence=evidence,
            why="There are documents waiting for human review.",
            why_not=(
                "Do not export unresolved review items.",
                "Do not auto-approve review items without reviewer evidence.",
            ),
            requires_human=True,
            human_escalation_reason="A reviewer should handle the queue before export.",
        )
    if documents_total == 0:
        return ActionRecommendation(
            action="Upload documents before operating the workflow",
            recommended_tool=None,
            risk=AgentToolRisk.READ_ONLY,
            confidence=AgentConfidence.MEDIUM,
            evidence=evidence,
            why="The workspace has no documents to process or review.",
            why_not=("No processing, review, or export action is available without documents.",),
        )
    return ActionRecommendation(
        action="Monitor workflow state",
        recommended_tool=AgentToolName.GET_METRICS_SUMMARY,
        risk=AgentToolRisk.READ_ONLY,
        confidence=AgentConfidence.MEDIUM,
        evidence=evidence,
        why="No review backlog is visible from the summary.",
        why_not=("No mutation is recommended from aggregate metrics alone.",),
    )


def _recommend_for_review_queue(
    data: Mapping[str, object],
    context: SecurityContext,
) -> ActionRecommendation:
    documents = data.get("documents")
    queue_count = len(documents) if isinstance(documents, list) else 0
    evidence = (f"review_queue_count={queue_count}",)
    if queue_count == 0:
        return ActionRecommendation(
            action="No review action needed",
            recommended_tool=AgentToolName.LIST_REVIEW_QUEUE,
            risk=AgentToolRisk.READ_ONLY,
            confidence=AgentConfidence.HIGH,
            evidence=evidence,
            why="The review queue is empty.",
            why_not=("Do not approve or reject documents that are not in the review queue.",),
        )
    return _tool_recommendation(
        tool_name=AgentToolName.SAVE_REVIEW_NOTES,
        context=context,
        action="Review the oldest queued document",
        evidence=evidence,
        why="The queue contains documents that need reviewer attention.",
        why_not=(
            "Do not export review items before approval.",
            "Do not reject without reviewer notes.",
        ),
        requires_human=True,
        human_escalation_reason="A human reviewer should inspect the queued document.",
    )


def _recommend_for_readiness(data: Mapping[str, object]) -> ActionRecommendation:
    status = str(data.get("status") or "unknown")
    checks = data.get("checks")
    evidence = (f"readiness={status}",)
    if isinstance(checks, Mapping):
        evidence = evidence + tuple(f"{key}={value}" for key, value in sorted(checks.items()))
    if status != "ready":
        return _human_escalation(
            evidence=evidence,
            reason="System readiness is not healthy enough for workflow actions.",
        )
    return ActionRecommendation(
        action="Continue operating workflow",
        recommended_tool=AgentToolName.GET_METRICS_SUMMARY,
        risk=AgentToolRisk.READ_ONLY,
        confidence=AgentConfidence.HIGH,
        evidence=evidence,
        why="Database and storage readiness checks are healthy.",
        why_not=("Readiness alone does not justify a mutation action.",),
    )


def _recommend_for_document_list(data: Mapping[str, object]) -> ActionRecommendation:
    documents = data.get("documents")
    count = len(documents) if isinstance(documents, list) else 0
    return ActionRecommendation(
        action="Inspect a specific document",
        recommended_tool=AgentToolName.GET_DOCUMENT_DETAIL if count else None,
        risk=AgentToolRisk.READ_ONLY,
        confidence=AgentConfidence.MEDIUM if count else AgentConfidence.LOW,
        evidence=(f"documents={count}",),
        why="Specific document evidence is needed before recommending workflow actions.",
        why_not=("Do not recommend processing, review, or export from a list alone.",),
        requires_human=count == 0,
        human_escalation_reason="Upload or select a document first." if count == 0 else None,
    )


def _tool_recommendation(
    *,
    tool_name: AgentToolName,
    context: SecurityContext,
    action: str,
    evidence: tuple[str, ...],
    why: str,
    why_not: tuple[str, ...],
    requires_human: bool = False,
    human_escalation_reason: str | None = None,
) -> ActionRecommendation:
    definition = get_tool_definition(tool_name)
    if not definition.can_be_called_by(context):
        return _human_escalation(
            evidence=evidence,
            reason=f"The current role cannot use {tool_name.value}.",
        )
    return ActionRecommendation(
        action=action,
        recommended_tool=tool_name,
        risk=definition.risk,
        confidence=AgentConfidence.HIGH,
        evidence=evidence,
        why=why,
        why_not=why_not,
        requires_confirmation=definition.requires_confirmation,
        requires_human=requires_human,
        human_escalation_reason=human_escalation_reason,
    )


def _human_escalation(
    *,
    evidence: tuple[str, ...],
    reason: str,
) -> ActionRecommendation:
    return ActionRecommendation(
        action="Escalate to human reviewer",
        recommended_tool=None,
        risk=AgentToolRisk.BLOCKED,
        confidence=AgentConfidence.LOW,
        evidence=evidence,
        why=reason,
        why_not=("No automated or recommended workflow action is safe with the current evidence.",),
        requires_human=True,
        human_escalation_reason=reason,
    )


def _validation_evidence(data: Mapping[str, object]) -> tuple[str, ...]:
    extraction = data.get("extraction")
    if not isinstance(extraction, Mapping):
        return ("validation_issues=unknown",)
    validation = extraction.get("validation")
    if not isinstance(validation, list):
        return ("validation_issues=unknown",)
    return (f"validation_issues={len(validation)}",)
