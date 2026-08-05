from __future__ import annotations

from dataclasses import dataclass

from app.agentops.service import AgentOpsEvaluationService
from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.evaluation.dashboard import EvaluationDashboardService


@dataclass(frozen=True)
class EvaluationModule:
    dashboard: EvaluationDashboardService
    agentops_service: AgentOpsEvaluationService


def build_evaluation_module(
    settings: Settings,
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> EvaluationModule:
    return EvaluationModule(
        dashboard=EvaluationDashboardService(
            settings=settings,
            history=persistence.benchmark_history,
            attempts=persistence.evaluation_attempts,
            parser=documents.parser,
            extractor=documents.extractor,
        ),
        agentops_service=AgentOpsEvaluationService(),
    )
