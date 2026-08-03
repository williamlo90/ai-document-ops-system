from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.documents.retention import (
    DocumentRetentionService,
    InMemoryRetentionRepository,
    RetentionRepository,
    SqliteRetentionRepository,
)
from app.metrics.services import MetricsService


@dataclass(frozen=True)
class OperationsModule:
    metrics_service: MetricsService
    retention_service: DocumentRetentionService


def build_operations_module(
    settings: Settings,
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> OperationsModule:
    return OperationsModule(
        metrics_service=_build_metrics_service(persistence),
        retention_service=_build_retention_service(settings, documents, persistence),
    )


def _build_metrics_service(persistence: PersistenceModule) -> MetricsService:
    repositories = persistence.documents
    return MetricsService(
        repositories.documents,
        repositories.jobs,
        repositories.audits,
        persistence.metrics_queries,
    )


def _build_retention_service(
    settings: Settings,
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> DocumentRetentionService:
    repository = _retention_repository(persistence)
    return DocumentRetentionService(
        settings=settings,
        storage=documents.storage,
        documents=persistence.documents.documents,
        repository=repository,
    )


def _retention_repository(persistence: PersistenceModule) -> RetentionRepository:
    if persistence.store is not None:
        return SqliteRetentionRepository(persistence.store)
    documents = persistence.documents
    backoffice = persistence.backoffice
    return InMemoryRetentionRepository(
        documents=documents.documents,
        jobs=documents.jobs,
        audits=documents.audits,
        extractions=documents.extractions,
        reviews=documents.reviews,
        corrections=documents.correction_events,
        work_items=backoffice.work_items,
        plans=backoffice.plans,
        drafts=backoffice.drafts,
        approvals=backoffice.approvals,
        policy_decisions=backoffice.policy_decisions,
        workflow_events=backoffice.workflow_events,
        agent_runs=persistence.agent_runs,
        scenario_evaluations=persistence.scenario_evaluations,
        notifications=persistence.notifications,
        integration_deliveries=persistence.integration_deliveries,
    )
