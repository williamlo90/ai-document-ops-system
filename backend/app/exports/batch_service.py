from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.settings import Settings
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
)
from app.documents.state_writer import DocumentStateWriter
from app.documents.workflow import DocumentWorkflowService
from app.exports.eligibility import ExportDestination, ExportEligibilityPolicy
from app.exports.execution import ExportExecutionLifecycle
from app.exports.models import (
    ExportBatchNotFound,
    ExportBatchRecord,
    ExportBatchStatus,
    ExportEligibilityError,
    ExportRunRecord,
)
from app.exports.repositories import ExportBatchRepository
from app.exports.services import InvoiceExportService
from app.exports.workspace import ExportWorkspaceQuery


class ExportBatchService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: ExportBatchRepository,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        invoice_exports: InvoiceExportService,
        transactions: TransactionManager | None = None,
        state_writer: DocumentStateWriter | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.documents = documents
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow
        self.invoice_exports = invoice_exports
        self.transactions = transactions or NoopTransactionManager()
        self.state_writer = state_writer or DocumentStateWriter(
            documents,
            audits,
            workflow,
            self.transactions,
        )

        self._eligibility = ExportEligibilityPolicy(
            repository=repository,
            documents=documents,
            extractions=extractions,
        )
        self._workspace = ExportWorkspaceQuery(
            settings=settings,
            repository=repository,
            documents=documents,
            audits=audits,
            eligibility=self._eligibility,
        )
        self._execution = ExportExecutionLifecycle(
            repository=repository,
            documents=documents,
            state_writer=self.state_writer,
            invoice_exports=invoice_exports,
            transactions=self.transactions,
            eligibility=self._eligibility,
            destinations=self._workspace.destinations,
        )

    def workspace(
        self,
        *,
        context: SecurityContext,
        view: str,
        search: str,
        vendor: str,
        currency: str,
        approved_by: str,
        page: int,
        page_size: int,
        batch_id: UUID | None,
    ) -> dict[str, object]:
        return self._workspace.workspace(
            context=context,
            view=view,
            search=search,
            vendor=vendor,
            currency=currency,
            approved_by=approved_by,
            page=page,
            page_size=page_size,
            batch_id=batch_id,
        )

    def capabilities(self) -> dict[str, object]:
        return self._workspace.capabilities()

    def create_batch(
        self,
        *,
        context: SecurityContext,
        document_ids: tuple[UUID, ...],
        mode: str,
        name: str | None,
    ) -> dict[str, object]:
        require_admin(context)
        destination = self._require_destination()
        unique_ids = tuple(dict.fromkeys(document_ids))
        if not unique_ids:
            raise ExportEligibilityError(
                "Select at least one invoice.",
                ({"code": "selection_required", "state": "failed", "label": "Invoices selected"},),
            )
        if mode == "draft":
            accepted, rejected = self._eligibility.workspace_documents(
                context.workspace_id,
                unique_ids,
            )
            status = ExportBatchStatus.DRAFT
        else:
            accepted, rejected = self._eligibility.eligible_documents(
                context.workspace_id,
                unique_ids,
            )
            status = ExportBatchStatus.READY
        if not accepted:
            raise ExportEligibilityError(
                "None of the selected invoices can be added.",
                tuple(
                    {"code": "invoice_rejected", "state": "failed", "label": item["reason"]}
                    for item in rejected
                ),
            )
        now = datetime.now(UTC)
        batch = ExportBatchRecord(
            workspace_id=context.workspace_id,
            document_ids=tuple(document.id for document in accepted),
            destination=str(destination["id"]),
            export_format=str(destination["formats"][0]),
            created_by=context.actor,
            status=status,
            name=name.strip() if name and name.strip() else None,
            created_at=now,
            updated_at=now,
        )
        self.repository.save_batch(batch)
        for document in accepted:
            self.audits.add(
                AuditEvent(
                    document_id=document.id,
                    event_type="export_draft_saved"
                    if status == ExportBatchStatus.DRAFT
                    else "export_batch_created",
                    actor=context.actor,
                    old_status=document.status,
                    new_status=document.status,
                    payload_summary=f"batch_id={batch.id}",
                )
            )
        return {
            "batch": self.batch_response(batch),
            "accepted": [str(document.id) for document in accepted],
            "rejected": rejected,
        }

    def update_batch(
        self,
        *,
        context: SecurityContext,
        batch_id: UUID,
        document_ids: tuple[UUID, ...],
        mode: str,
        name: str | None,
    ) -> dict[str, object]:
        require_admin(context)
        current = self._batch(context.workspace_id, batch_id)
        if current.status in {ExportBatchStatus.RUNNING, ExportBatchStatus.COMPLETED}:
            raise ExportEligibilityError(
                "This export batch can no longer be edited.",
                ({"code": "batch_locked", "state": "failed", "label": "Batch is locked"},),
            )
        unique_ids = tuple(dict.fromkeys(document_ids))
        if mode == "draft":
            accepted, rejected = self._eligibility.workspace_documents(
                context.workspace_id,
                unique_ids,
                exclude_batch_id=current.id,
            )
            next_status = ExportBatchStatus.DRAFT
        else:
            accepted, rejected = self._eligibility.eligible_documents(
                context.workspace_id,
                unique_ids,
                exclude_batch_id=current.id,
            )
            next_status = ExportBatchStatus.READY
        updated = replace(
            current,
            document_ids=tuple(document.id for document in accepted),
            status=next_status,
            name=name.strip() if name and name.strip() else current.name,
            updated_at=datetime.now(UTC),
        )
        self.repository.save_batch(updated)
        return {
            "batch": self.batch_response(updated),
            "accepted": [str(document.id) for document in accepted],
            "rejected": rejected,
        }

    def execute(
        self,
        *,
        context: SecurityContext,
        batch_id: UUID,
        idempotency_key: str,
    ) -> ExportRunRecord:
        return self._execution.execute(
            context=context,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
        )

    def retry(
        self,
        *,
        context: SecurityContext,
        run_id: UUID,
        idempotency_key: str,
    ) -> ExportRunRecord:
        return self._execution.retry(
            context=context,
            run_id=run_id,
            idempotency_key=idempotency_key,
        )

    def eligibility(
        self,
        *,
        context: SecurityContext,
        batch: ExportBatchRecord,
    ) -> list[dict[str, object]]:
        return self._eligibility.checks(
            context=context,
            batch=batch,
            destinations=self._workspace.destinations(),
        )

    def batch_response(self, batch: ExportBatchRecord) -> dict[str, object]:
        return self._workspace.batch_response(batch)

    def run_response(
        self,
        run: ExportRunRecord,
        document_map: dict[UUID, DocumentRecord] | None = None,
    ) -> dict[str, object]:
        return self._workspace.run_response(run, document_map)

    def run_detail(self, context: SecurityContext, run_id: UUID) -> dict[str, object]:
        return self._workspace.run_detail(context, run_id)

    def artifact(self, context: SecurityContext, run_id: UUID) -> tuple[str, str]:
        return self._workspace.artifact(context, run_id)

    def _batch(self, workspace_id: str, batch_id: UUID) -> ExportBatchRecord:
        batch = self.repository.get_batch(workspace_id, batch_id)
        if batch is None:
            raise ExportBatchNotFound("Export batch not found.")
        return batch

    def _require_destination(self) -> ExportDestination:
        destinations = self._workspace.destinations()
        if not destinations:
            raise ExportEligibilityError(
                "No supported batch export destination is configured.",
                (
                    {
                        "code": "destination_unavailable",
                        "state": "failed",
                        "label": "Destination is unavailable",
                    },
                ),
            )
        return destinations[0]
