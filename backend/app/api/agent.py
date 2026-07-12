from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agent.contracts import AgentToolName
from app.agent.service import CopilotRequest
from app.api.dependencies import AppContainer, get_container, require_admin_context
from app.core.security import SecurityContext


router = APIRouter(prefix="/agent", tags=["agent"])


class CopilotRequestPayload(BaseModel):
    message: str
    document_id: UUID | None = None
    expected_tool: AgentToolName | None = None
    execute_tool: AgentToolName | None = None
    confirmed: bool = False


@router.post("/copilot")
def read_only_copilot(
    payload: CopilotRequestPayload,
    context: SecurityContext = Depends(require_admin_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    result = container.copilot_service.answer(
        CopilotRequest(
            message=payload.message,
            document_id=payload.document_id,
            expected_tool=payload.expected_tool,
            execute_tool=payload.execute_tool,
            confirmed=payload.confirmed,
        ),
        context,
    )
    return _copilot_response(result)


def _copilot_response(result) -> dict[str, object]:
    run = result.run
    response = result.tool_response
    return {
        "run": {
            "id": str(run.id),
            "workspace_id": run.workspace_id,
            "actor": run.actor,
            "intent": run.intent,
            "prompt_version": run.prompt_version,
            "confidence": run.confidence.value,
            "expected_tool": run.expected_tool.value if run.expected_tool else None,
            "selected_tool": run.selected_tool.value if run.selected_tool else None,
            "selection_reason": run.selection_reason,
            "why_not": run.why_not,
            "human_escalation_reason": run.human_escalation_reason,
            "failure_type": run.failure_type.value if run.failure_type else None,
            "final_summary": run.final_summary,
            "blocked_actions": run.blocked_actions,
            "tool_calls": [
                {
                    "id": str(trace.id),
                    "tool_name": trace.tool_name.value,
                    "risk": trace.risk.value,
                    "status": trace.status,
                    "summary": trace.summary,
                    "confidence": trace.confidence.value,
                    "evidence": list(trace.evidence),
                    "failure_type": trace.failure_type.value if trace.failure_type else None,
                    "human_escalation_reason": trace.human_escalation_reason,
                }
                for trace in run.tool_calls
            ],
        },
        "response": {
            "tool_name": response.tool_name.value,
            "status": response.status,
            "risk": response.risk.value,
            "summary": response.summary,
            "confidence": response.confidence.value,
            "evidence": list(response.evidence),
            "data": dict(response.data),
            "requires_follow_up": response.requires_follow_up,
            "failure_type": response.failure_type.value if response.failure_type else None,
            "human_escalation_reason": response.human_escalation_reason,
        },
    }
