from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.agent.repositories import (
    AgentRunRepository,
    InMemoryAgentRunRepository,
    SqliteAgentRunRepository,
)
from app.agentops.repositories import (
    InMemoryScenarioEvaluationRepository,
    ScenarioEvaluationRepository,
    SqliteScenarioEvaluationRepository,
)
from app.backoffice.repositories import (
    ActionDraftRepository,
    ApprovalRepository,
    InMemoryActionDraftRepository,
    InMemoryApprovalRepository,
    InMemoryPolicyDecisionRepository,
    InMemoryTaskPlanRepository,
    InMemoryWorkflowEventRepository,
    InMemoryWorkItemRepository,
    PolicyDecisionRepository,
    TaskPlanRepository,
    WorkItemRepository,
    WorkflowEventRepository,
)
from app.backoffice.sqlite_repositories import (
    SqliteActionDraftRepository,
    SqliteApprovalRepository,
    SqlitePolicyDecisionRepository,
    SqliteTaskPlanRepository,
    SqliteWorkflowEventRepository,
    SqliteWorkItemRepository,
)
from app.benchmark.history import (
    BenchmarkHistoryRepository,
    InMemoryBenchmarkHistoryRepository,
    SqliteBenchmarkHistoryRepository,
)
from app.core.settings import Settings, is_hosted
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryExtractionRepository,
    InMemoryJobRepository,
    InMemoryReviewTaskRepository,
    JobRepository,
    ReviewTaskRepository,
)
from app.documents.sqlite_repositories import (
    SqliteAuditRepository,
    SqliteDocumentRepository,
    SqliteExtractionRepository,
    SqliteJobRepository,
    SqliteReviewTaskRepository,
    SqliteStore,
)
from app.evaluation.history import (
    EvaluationAttemptRepository,
    InMemoryEvaluationAttemptRepository,
    SqliteEvaluationAttemptRepository,
)
from app.exports.repositories import (
    ExportBatchRepository,
    InMemoryExportBatchRepository,
    SqliteExportBatchRepository,
)
from app.integrations.repositories import (
    InMemoryIntegrationDeliveryRepository,
    IntegrationDeliveryRepository,
    SqliteIntegrationDeliveryRepository,
)
from app.invoices.queries import InvoiceQueryRepository, SqliteInvoiceQueryRepository
from app.metrics.queries import MetricsQueryRepository, SqliteMetricsQueryRepository
from app.operations.notifications import (
    InMemoryNotificationRepository,
    NotificationRepository,
    SqliteNotificationRepository,
)
from app.operations.queries import OperationsQueryRepository, SqliteOperationsQueryRepository
from app.providers.queries import ProviderHealthQueryRepository, SqliteProviderHealthQueryRepository
from app.review.repositories import (
    CorrectionEventRepository,
    InMemoryCorrectionEventRepository,
)
from app.review.sqlite_repositories import SqliteCorrectionEventRepository


@dataclass(frozen=True)
class DocumentRepositories:
    documents: DocumentRepository
    jobs: JobRepository
    audits: AuditRepository
    extractions: ExtractionRepository
    reviews: ReviewTaskRepository
    correction_events: CorrectionEventRepository


@dataclass(frozen=True)
class BackofficeRepositories:
    work_items: WorkItemRepository
    plans: TaskPlanRepository
    drafts: ActionDraftRepository
    approvals: ApprovalRepository
    policy_decisions: PolicyDecisionRepository
    workflow_events: WorkflowEventRepository


@dataclass(frozen=True)
class PersistenceModule:
    store: SqliteStore | None
    transactions: TransactionManager
    documents: DocumentRepositories
    backoffice: BackofficeRepositories
    benchmark_history: BenchmarkHistoryRepository
    evaluation_attempts: EvaluationAttemptRepository
    agent_runs: AgentRunRepository
    scenario_evaluations: ScenarioEvaluationRepository
    notifications: NotificationRepository
    integration_deliveries: IntegrationDeliveryRepository
    export_batches: ExportBatchRepository
    invoice_queries: InvoiceQueryRepository | None
    metrics_queries: MetricsQueryRepository | None
    provider_health_queries: ProviderHealthQueryRepository | None
    operations_queries: OperationsQueryRepository | None


def build_persistence_module(settings: Settings) -> PersistenceModule:
    backend = _metadata_backend(settings)
    if backend == "sqlite":
        return _sqlite_module(settings)
    if backend == "memory":
        return _memory_module()
    raise ValueError(f"Unsupported storage backend: {backend}")


def _metadata_backend(settings: Settings) -> str:
    backend = settings.storage_backend.strip().lower()
    if backend == "memory" and is_hosted(settings):
        raise ValueError(
            "Hosted mode requires persistent sqlite storage; "
            "memory storage is for local tests only."
        )
    return backend


def _sqlite_module(settings: Settings) -> PersistenceModule:
    store = SqliteStore(Path(settings.sqlite_path))
    documents = DocumentRepositories(
        documents=SqliteDocumentRepository(store),
        jobs=SqliteJobRepository(store),
        audits=SqliteAuditRepository(store),
        extractions=SqliteExtractionRepository(store),
        reviews=SqliteReviewTaskRepository(store),
        correction_events=SqliteCorrectionEventRepository(store),
    )
    backoffice = BackofficeRepositories(
        work_items=SqliteWorkItemRepository(store),
        plans=SqliteTaskPlanRepository(store),
        drafts=SqliteActionDraftRepository(store),
        approvals=SqliteApprovalRepository(store),
        policy_decisions=SqlitePolicyDecisionRepository(store),
        workflow_events=SqliteWorkflowEventRepository(store),
    )
    return PersistenceModule(
        store=store,
        transactions=store,
        documents=documents,
        backoffice=backoffice,
        benchmark_history=SqliteBenchmarkHistoryRepository(store),
        evaluation_attempts=SqliteEvaluationAttemptRepository(store),
        agent_runs=SqliteAgentRunRepository(store),
        scenario_evaluations=SqliteScenarioEvaluationRepository(store),
        notifications=SqliteNotificationRepository(store),
        integration_deliveries=SqliteIntegrationDeliveryRepository(store),
        export_batches=SqliteExportBatchRepository(store),
        invoice_queries=SqliteInvoiceQueryRepository(store),
        metrics_queries=SqliteMetricsQueryRepository(store),
        provider_health_queries=SqliteProviderHealthQueryRepository(store),
        operations_queries=SqliteOperationsQueryRepository(store),
    )


def _memory_module() -> PersistenceModule:
    documents = DocumentRepositories(
        documents=InMemoryDocumentRepository(),
        jobs=InMemoryJobRepository(),
        audits=InMemoryAuditRepository(),
        extractions=InMemoryExtractionRepository(),
        reviews=InMemoryReviewTaskRepository(),
        correction_events=InMemoryCorrectionEventRepository(),
    )
    backoffice = BackofficeRepositories(
        work_items=InMemoryWorkItemRepository(),
        plans=InMemoryTaskPlanRepository(),
        drafts=InMemoryActionDraftRepository(),
        approvals=InMemoryApprovalRepository(),
        policy_decisions=InMemoryPolicyDecisionRepository(),
        workflow_events=InMemoryWorkflowEventRepository(),
    )
    return PersistenceModule(
        store=None,
        transactions=NoopTransactionManager(),
        documents=documents,
        backoffice=backoffice,
        benchmark_history=InMemoryBenchmarkHistoryRepository(),
        evaluation_attempts=InMemoryEvaluationAttemptRepository(),
        agent_runs=InMemoryAgentRunRepository(),
        scenario_evaluations=InMemoryScenarioEvaluationRepository(),
        notifications=InMemoryNotificationRepository(),
        integration_deliveries=InMemoryIntegrationDeliveryRepository(),
        export_batches=InMemoryExportBatchRepository(),
        invoice_queries=None,
        metrics_queries=None,
        provider_health_queries=None,
        operations_queries=None,
    )
