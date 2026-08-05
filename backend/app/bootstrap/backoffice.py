from __future__ import annotations

from dataclasses import dataclass

from app.agent.tools import ControlledToolExecutor
from app.backoffice.services import BackofficeWorkflowService
from app.bootstrap.persistence import PersistenceModule


@dataclass(frozen=True)
class BackofficeModule:
    service: BackofficeWorkflowService


def build_backoffice_module(
    tool_executor: ControlledToolExecutor,
    persistence: PersistenceModule,
) -> BackofficeModule:
    repositories = persistence.backoffice
    return BackofficeModule(
        service=BackofficeWorkflowService(
            work_items=repositories.work_items,
            plans=repositories.plans,
            drafts=repositories.drafts,
            approvals=repositories.approvals,
            policy_decisions=repositories.policy_decisions,
            workflow_events=repositories.workflow_events,
            tool_executor=tool_executor,
            agent_runs=persistence.agent_runs,
            documents=persistence.documents.documents,
            transactions=persistence.transactions,
        )
    )
