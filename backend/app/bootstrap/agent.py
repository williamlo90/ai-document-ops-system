from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.agent.service import ReadOnlyCopilotService
from app.agent.tools import ControlledToolExecutor
from app.bootstrap.documents import DocumentModule
from app.bootstrap.exports import ExportModule
from app.bootstrap.persistence import PersistenceModule
from app.bootstrap.review import ReviewModule
from app.integrations.services import InvoiceIntegrationService


@dataclass(frozen=True)
class AgentModule:
    tool_executor: ControlledToolExecutor
    copilot_service: ReadOnlyCopilotService


def build_agent_module(
    *,
    documents: DocumentModule,
    review: ReviewModule,
    exports: ExportModule,
    integration_service: InvoiceIntegrationService,
    persistence: PersistenceModule,
    readiness: Callable[[], dict[str, bool]],
) -> AgentModule:
    repositories = persistence.documents
    tool_executor = ControlledToolExecutor(
        processing_service=documents.processing_service,
        export_service=exports.service,
        integration_service=integration_service,
    )
    copilot_service = ReadOnlyCopilotService(
        documents=repositories.documents,
        jobs=repositories.jobs,
        audits=repositories.audits,
        extractions=repositories.extractions,
        review_service=review.service,
        agent_runs=persistence.agent_runs,
        tool_executor=tool_executor,
        readiness=readiness,
    )
    return AgentModule(tool_executor=tool_executor, copilot_service=copilot_service)
