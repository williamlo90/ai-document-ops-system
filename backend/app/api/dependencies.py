from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from app.agent.repositories import (
    AgentRunRepository,
    InMemoryAgentRunRepository,
    SqliteAgentRunRepository,
)
from app.agent.service import ReadOnlyCopilotService
from app.agent.tools import ControlledToolExecutor
from app.agentops.service import AgentOpsEvaluationService
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
from app.backoffice.services import BackofficeWorkflowService
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
from app.core.security import (
    SecurityContext,
    UnauthorizedError,
    authenticate_access_token,
    authenticate_metrics_token,
    require_any_role,
)
from app.core.upload_scanning import build_upload_scanner
from app.core.settings import Settings
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
from app.documents.services import DocumentProcessingService, DocumentUploadService
from app.documents.retention import (
    DocumentRetentionService,
    InMemoryRetentionRepository,
    SqliteRetentionRepository,
)
from app.documents.sqlite_repositories import (
    SqliteAuditRepository,
    SqliteDocumentRepository,
    SqliteExtractionRepository,
    SqliteJobRepository,
    SqliteReviewTaskRepository,
    SqliteStore,
)
from app.documents.worker import DocumentProcessingWorker
from app.documents.workflow import DocumentWorkflowService
from app.exports.services import InvoiceExportService
from app.exports.batch_service import ExportBatchService
from app.exports.repositories import (
    ExportBatchRepository,
    InMemoryExportBatchRepository,
    SqliteExportBatchRepository,
)
from app.integrations.adapters import MockAccountingAdapter
from app.integrations.repositories import (
    InMemoryIntegrationDeliveryRepository,
    IntegrationDeliveryRepository,
    SqliteIntegrationDeliveryRepository,
)
from app.integrations.services import InvoiceIntegrationService
from app.metrics.services import MetricsService
from app.providers.factory import build_extractor_provider, build_parser_provider
from app.providers.storage import DocumentStorage, build_document_storage
from app.operations.notifications import (
    InMemoryNotificationRepository,
    NotificationRepository,
    SqliteNotificationRepository,
)
from app.review.services import ReviewService
from app.review.corrections import CorrectionFeedbackService
from app.review.repositories import (
    CorrectionEventRepository,
    InMemoryCorrectionEventRepository,
)
from app.review.sqlite_repositories import SqliteCorrectionEventRepository


@dataclass
class AppContainer:
    settings: Settings
    storage: DocumentStorage
    documents: DocumentRepository
    jobs: JobRepository
    audits: AuditRepository
    extractions: ExtractionRepository
    reviews: ReviewTaskRepository
    correction_events: CorrectionEventRepository
    benchmark_history: BenchmarkHistoryRepository
    workflow: DocumentWorkflowService
    upload_service: DocumentUploadService
    processing_service: DocumentProcessingService
    worker_service: DocumentProcessingWorker
    review_service: ReviewService
    correction_feedback: CorrectionFeedbackService
    export_service: InvoiceExportService
    export_batches: ExportBatchRepository
    export_batch_service: ExportBatchService
    integration_deliveries: IntegrationDeliveryRepository
    integration_service: InvoiceIntegrationService
    metrics_service: MetricsService
    agent_runs: AgentRunRepository
    agentops_service: AgentOpsEvaluationService
    scenario_evaluations: ScenarioEvaluationRepository
    notifications: NotificationRepository
    tool_executor: ControlledToolExecutor
    copilot_service: ReadOnlyCopilotService
    backoffice_work_items: WorkItemRepository
    backoffice_plans: TaskPlanRepository
    backoffice_drafts: ActionDraftRepository
    backoffice_approvals: ApprovalRepository
    backoffice_policy_decisions: PolicyDecisionRepository
    workflow_events: WorkflowEventRepository
    backoffice_service: BackofficeWorkflowService
    retention_service: DocumentRetentionService

    def readiness(self) -> dict[str, bool]:
        return {
            "database": _repository_ready(self.documents),
            "storage": _storage_ready(self.storage),
        }

    def close(self) -> None:
        store = getattr(self.documents, "store", None)
        close = getattr(store, "close", None)
        if callable(close):
            close()


def build_container(settings: Settings) -> AppContainer:
    storage = build_document_storage(
        settings.document_storage_backend,
        Path(settings.upload_root),
        max_upload_bytes=settings.max_upload_bytes,
        s3_endpoint_url=settings.s3_endpoint_url or "",
        s3_bucket=settings.s3_bucket or "",
        s3_region=settings.s3_region or "auto",
        s3_access_key_id=settings.s3_access_key_id or "",
        s3_secret_access_key=settings.s3_secret_access_key or "",
    )
    if settings.storage_backend.strip().lower() == "sqlite":
        store = SqliteStore(Path(settings.sqlite_path))
        documents = SqliteDocumentRepository(store)
        jobs = SqliteJobRepository(store)
        audits = SqliteAuditRepository(store)
        extractions = SqliteExtractionRepository(store)
        reviews = SqliteReviewTaskRepository(store)
        correction_events = SqliteCorrectionEventRepository(store)
        benchmark_history = SqliteBenchmarkHistoryRepository(store)
        backoffice_work_items = SqliteWorkItemRepository(store)
        backoffice_plans = SqliteTaskPlanRepository(store)
        backoffice_drafts = SqliteActionDraftRepository(store)
        backoffice_approvals = SqliteApprovalRepository(store)
        backoffice_policy_decisions = SqlitePolicyDecisionRepository(store)
        workflow_events = SqliteWorkflowEventRepository(store)
        agent_runs = SqliteAgentRunRepository(store)
        scenario_evaluations = SqliteScenarioEvaluationRepository(store)
        notifications = SqliteNotificationRepository(store)
        integration_deliveries = SqliteIntegrationDeliveryRepository(store)
        export_batches = SqliteExportBatchRepository(store)
    elif settings.storage_backend.strip().lower() == "memory":
        documents = InMemoryDocumentRepository()
        jobs = InMemoryJobRepository()
        audits = InMemoryAuditRepository()
        extractions = InMemoryExtractionRepository()
        reviews = InMemoryReviewTaskRepository()
        correction_events = InMemoryCorrectionEventRepository()
        benchmark_history = InMemoryBenchmarkHistoryRepository()
        backoffice_work_items = InMemoryWorkItemRepository()
        backoffice_plans = InMemoryTaskPlanRepository()
        backoffice_drafts = InMemoryActionDraftRepository()
        backoffice_approvals = InMemoryApprovalRepository()
        backoffice_policy_decisions = InMemoryPolicyDecisionRepository()
        workflow_events = InMemoryWorkflowEventRepository()
        agent_runs = InMemoryAgentRunRepository()
        scenario_evaluations = InMemoryScenarioEvaluationRepository()
        notifications = InMemoryNotificationRepository()
        integration_deliveries = InMemoryIntegrationDeliveryRepository()
        export_batches = InMemoryExportBatchRepository()
    else:
        raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
    agentops_service = AgentOpsEvaluationService()
    workflow = DocumentWorkflowService()
    upload_scanner = build_upload_scanner(settings)
    upload_service = DocumentUploadService(
        storage, documents, jobs, audits, workflow, upload_scanner
    )
    processing_service = DocumentProcessingService(
        storage,
        documents,
        jobs,
        audits,
        extractions,
        workflow,
        build_parser_provider(settings),
        build_extractor_provider(settings),
        max_processing_attempts=settings.max_processing_attempts,
    )
    worker_service = DocumentProcessingWorker(jobs, processing_service)
    correction_feedback = CorrectionFeedbackService(correction_events)
    review_service = ReviewService(
        documents,
        reviews,
        extractions,
        audits,
        workflow,
        correction_feedback,
    )
    export_service = InvoiceExportService(documents, extractions, audits, workflow)
    export_batch_service = ExportBatchService(
        settings=settings,
        repository=export_batches,
        documents=documents,
        extractions=extractions,
        audits=audits,
        workflow=workflow,
        invoice_exports=export_service,
    )
    integration_service = InvoiceIntegrationService(
        documents,
        extractions,
        audits,
        workflow,
        MockAccountingAdapter(),
        integration_deliveries,
    )
    metrics_service = MetricsService(documents, jobs, audits)
    tool_executor = ControlledToolExecutor(
        processing_service=processing_service,
        export_service=export_service,
        integration_service=integration_service,
    )
    copilot_service = ReadOnlyCopilotService(
        documents=documents,
        jobs=jobs,
        audits=audits,
        extractions=extractions,
        review_service=review_service,
        agent_runs=agent_runs,
        tool_executor=tool_executor,
        readiness=lambda: {
            "database": _repository_ready(documents),
            "storage": _storage_ready(storage),
        },
    )
    backoffice_service = BackofficeWorkflowService(
        work_items=backoffice_work_items,
        plans=backoffice_plans,
        drafts=backoffice_drafts,
        approvals=backoffice_approvals,
        policy_decisions=backoffice_policy_decisions,
        workflow_events=workflow_events,
        tool_executor=tool_executor,
        agent_runs=agent_runs,
        documents=documents,
    )
    if settings.storage_backend.strip().lower() == "sqlite":
        retention_repository = SqliteRetentionRepository(store)
    else:
        retention_repository = InMemoryRetentionRepository(
            documents=documents,
            jobs=jobs,
            audits=audits,
            extractions=extractions,
            reviews=reviews,
            corrections=correction_events,
            work_items=backoffice_work_items,
            plans=backoffice_plans,
            drafts=backoffice_drafts,
            approvals=backoffice_approvals,
            policy_decisions=backoffice_policy_decisions,
            workflow_events=workflow_events,
            agent_runs=agent_runs,
            scenario_evaluations=scenario_evaluations,
            notifications=notifications,
            integration_deliveries=integration_deliveries,
        )
    retention_service = DocumentRetentionService(
        settings=settings,
        storage=storage,
        documents=documents,
        repository=retention_repository,
    )
    return AppContainer(
        settings=settings,
        storage=storage,
        documents=documents,
        jobs=jobs,
        audits=audits,
        extractions=extractions,
        reviews=reviews,
        correction_events=correction_events,
        benchmark_history=benchmark_history,
        workflow=workflow,
        upload_service=upload_service,
        processing_service=processing_service,
        worker_service=worker_service,
        review_service=review_service,
        correction_feedback=correction_feedback,
        export_service=export_service,
        export_batches=export_batches,
        export_batch_service=export_batch_service,
        integration_deliveries=integration_deliveries,
        integration_service=integration_service,
        metrics_service=metrics_service,
        agent_runs=agent_runs,
        agentops_service=agentops_service,
        scenario_evaluations=scenario_evaluations,
        notifications=notifications,
        tool_executor=tool_executor,
        copilot_service=copilot_service,
        backoffice_work_items=backoffice_work_items,
        backoffice_plans=backoffice_plans,
        backoffice_drafts=backoffice_drafts,
        backoffice_approvals=backoffice_approvals,
        backoffice_policy_decisions=backoffice_policy_decisions,
        workflow_events=workflow_events,
        backoffice_service=backoffice_service,
        retention_service=retention_service,
    )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def require_admin_context(
    request: Request,
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    session_id: str | None = Cookie(default=None, alias="doc_intel_admin_token"),
) -> SecurityContext:
    settings = get_container(request).settings
    session_context = request.app.state.sessions.get(session_id)
    if session_context is not None:
        return session_context
    try:
        return authenticate_access_token(x_access_token or x_admin_token, settings)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from exc


def require_metrics_token(
    request: Request,
    x_metrics_token: str | None = Header(default=None, alias="X-Metrics-Token"),
) -> None:
    settings = get_container(request).settings
    try:
        authenticate_metrics_token(x_metrics_token, settings)
    except UnauthorizedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from exc


def require_review_context(
    context: SecurityContext = Depends(require_admin_context),
) -> SecurityContext:
    try:
        require_any_role(context, {"admin", "reviewer"})
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden") from exc
    return context


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
            return upload_root.exists()
        return True
    except Exception:
        return False
