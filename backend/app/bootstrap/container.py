from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.agent.repositories import AgentRunRepository
from app.agent.service import ReadOnlyCopilotService
from app.agent.tools import ControlledToolExecutor
from app.agentops.repositories import ScenarioEvaluationRepository
from app.agentops.service import AgentOpsEvaluationService
from app.backoffice.repositories import (
    ActionDraftRepository,
    ApprovalRepository,
    PolicyDecisionRepository,
    TaskPlanRepository,
    WorkItemRepository,
    WorkflowEventRepository,
)
from app.backoffice.services import BackofficeWorkflowService
from app.benchmark.history import BenchmarkHistoryRepository
from app.bootstrap.agent import AgentModule, build_agent_module
from app.bootstrap.backoffice import BackofficeModule, build_backoffice_module
from app.bootstrap.documents import DocumentModule, build_document_module
from app.bootstrap.evaluation import EvaluationModule, build_evaluation_module
from app.bootstrap.exports import ExportModule, build_export_module
from app.bootstrap.integrations import IntegrationModule, build_integration_module
from app.bootstrap.operations import OperationsModule, build_operations_module
from app.bootstrap.persistence import PersistenceModule, build_persistence_module
from app.bootstrap.review import ReviewModule, build_review_module
from app.core.security import SessionStore
from app.core.settings import Settings
from app.core.transactions import TransactionManager
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
    ReviewTaskRepository,
)
from app.documents.retention import DocumentRetentionService
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.worker import DocumentProcessingWorker
from app.documents.workflow import DocumentWorkflowService
from app.evaluation.dashboard import EvaluationDashboardService
from app.evaluation.history import EvaluationAttemptRepository
from app.exports.batch_service import ExportBatchService
from app.exports.repositories import ExportBatchRepository
from app.exports.services import InvoiceExportService
from app.integrations.repositories import IntegrationDeliveryRepository
from app.integrations.services import InvoiceIntegrationService
from app.invoices.queries import InvoiceQueryRepository
from app.metrics.queries import MetricsQueryRepository
from app.metrics.services import MetricsService
from app.operations.notifications import NotificationRepository
from app.operations.queries import OperationsQueryRepository
from app.providers.queries import ProviderHealthQueryRepository
from app.providers.storage import DocumentStorage
from app.review.corrections import CorrectionFeedbackService
from app.review.repositories import CorrectionEventRepository
from app.review.services import ReviewService


@dataclass
class AppContainer:
    settings: Settings
    sessions: SessionStore
    persistence: PersistenceModule
    document_module: DocumentModule
    review_module: ReviewModule
    export_module: ExportModule
    integration_module: IntegrationModule
    evaluation_module: EvaluationModule
    operations_module: OperationsModule
    agent_module: AgentModule
    backoffice_module: BackofficeModule

    @property
    def storage(self) -> DocumentStorage:
        return self.document_module.storage

    @property
    def documents(self) -> DocumentRepository:
        return self.persistence.documents.documents

    @property
    def jobs(self) -> JobRepository:
        return self.persistence.documents.jobs

    @property
    def audits(self) -> AuditRepository:
        return self.persistence.documents.audits

    @property
    def extractions(self) -> ExtractionRepository:
        return self.persistence.documents.extractions

    @property
    def reviews(self) -> ReviewTaskRepository:
        return self.persistence.documents.reviews

    @property
    def correction_events(self) -> CorrectionEventRepository:
        return self.persistence.documents.correction_events

    @property
    def benchmark_history(self) -> BenchmarkHistoryRepository:
        return self.persistence.benchmark_history

    @property
    def evaluation_attempts(self) -> EvaluationAttemptRepository:
        return self.persistence.evaluation_attempts

    @property
    def evaluation_dashboard(self) -> EvaluationDashboardService:
        return self.evaluation_module.dashboard

    @property
    def workflow(self) -> DocumentWorkflowService:
        return self.document_module.workflow

    @property
    def upload_service(self) -> DocumentUploadService:
        return self.document_module.upload_service

    @property
    def processing_service(self) -> DocumentProcessingService:
        return self.document_module.processing_service

    @property
    def worker_service(self) -> DocumentProcessingWorker:
        return self.document_module.worker_service

    @property
    def review_service(self) -> ReviewService:
        return self.review_module.service

    @property
    def correction_feedback(self) -> CorrectionFeedbackService:
        return self.review_module.correction_feedback

    @property
    def export_service(self) -> InvoiceExportService:
        return self.export_module.service

    @property
    def export_batches(self) -> ExportBatchRepository:
        return self.persistence.export_batches

    @property
    def export_batch_service(self) -> ExportBatchService:
        return self.export_module.batch_service

    @property
    def integration_deliveries(self) -> IntegrationDeliveryRepository:
        return self.persistence.integration_deliveries

    @property
    def integration_service(self) -> InvoiceIntegrationService:
        return self.integration_module.service

    @property
    def metrics_service(self) -> MetricsService:
        return self.operations_module.metrics_service

    @property
    def agent_runs(self) -> AgentRunRepository:
        return self.persistence.agent_runs

    @property
    def agentops_service(self) -> AgentOpsEvaluationService:
        return self.evaluation_module.agentops_service

    @property
    def scenario_evaluations(self) -> ScenarioEvaluationRepository:
        return self.persistence.scenario_evaluations

    @property
    def notifications(self) -> NotificationRepository:
        return self.persistence.notifications

    @property
    def tool_executor(self) -> ControlledToolExecutor:
        return self.agent_module.tool_executor

    @property
    def copilot_service(self) -> ReadOnlyCopilotService:
        return self.agent_module.copilot_service

    @property
    def backoffice_work_items(self) -> WorkItemRepository:
        return self.persistence.backoffice.work_items

    @property
    def backoffice_plans(self) -> TaskPlanRepository:
        return self.persistence.backoffice.plans

    @property
    def backoffice_drafts(self) -> ActionDraftRepository:
        return self.persistence.backoffice.drafts

    @property
    def backoffice_approvals(self) -> ApprovalRepository:
        return self.persistence.backoffice.approvals

    @property
    def backoffice_policy_decisions(self) -> PolicyDecisionRepository:
        return self.persistence.backoffice.policy_decisions

    @property
    def workflow_events(self) -> WorkflowEventRepository:
        return self.persistence.backoffice.workflow_events

    @property
    def backoffice_service(self) -> BackofficeWorkflowService:
        return self.backoffice_module.service

    @property
    def retention_service(self) -> DocumentRetentionService:
        return self.operations_module.retention_service

    @property
    def transactions(self) -> TransactionManager:
        return self.persistence.transactions

    @property
    def invoice_queries(self) -> InvoiceQueryRepository | None:
        return self.persistence.invoice_queries

    @property
    def metrics_queries(self) -> MetricsQueryRepository | None:
        return self.persistence.metrics_queries

    @property
    def provider_health_queries(self) -> ProviderHealthQueryRepository | None:
        return self.persistence.provider_health_queries

    @property
    def operations_queries(self) -> OperationsQueryRepository | None:
        return self.persistence.operations_queries

    def readiness(self) -> dict[str, bool]:
        return _module_readiness(self.document_module, self.persistence)

    def close(self) -> None:
        if self.persistence.store is not None:
            self.persistence.store.close()


def build_container(settings: Settings) -> AppContainer:
    persistence = build_persistence_module(settings)
    documents = build_document_module(settings, persistence)
    review = build_review_module(documents, persistence)
    exports = build_export_module(settings, documents, persistence)
    integration = build_integration_module(documents, persistence)
    evaluation = build_evaluation_module(settings, documents, persistence)
    operations = build_operations_module(settings, documents, persistence)
    agent = build_agent_module(
        documents=documents,
        review=review,
        exports=exports,
        integration_service=integration.service,
        persistence=persistence,
        readiness=lambda: _module_readiness(documents, persistence),
    )
    backoffice = build_backoffice_module(agent.tool_executor, persistence)
    return AppContainer(
        settings=settings,
        sessions=SessionStore(settings.session_ttl_seconds),
        persistence=persistence,
        document_module=documents,
        review_module=review,
        export_module=exports,
        integration_module=integration,
        evaluation_module=evaluation,
        operations_module=operations,
        agent_module=agent,
        backoffice_module=backoffice,
    )


def _module_readiness(
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> dict[str, bool]:
    return {
        "database": _repository_ready(persistence.documents.documents),
        "storage": _storage_ready(documents.storage),
    }


def _repository_ready(repository: DocumentRepository) -> bool:
    try:
        repository.list_all()
        return True
    except Exception:
        return False


def _storage_ready(storage: DocumentStorage) -> bool:
    try:
        upload_root = getattr(storage, "upload_root", None)
        if upload_root is not None:
            return cast(Path, upload_root).exists()
        return True
    except Exception:
        return False
