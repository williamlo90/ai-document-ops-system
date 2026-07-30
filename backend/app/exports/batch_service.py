from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import RLock
from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.settings import Settings
from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
    StoredExtraction,
)
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService
from app.exports.models import (
    ExportBatchNotFound,
    ExportBatchRecord,
    ExportBatchStatus,
    ExportEligibilityError,
    ExportIdempotencyConflict,
    ExportRunNotFound,
    ExportRunRecord,
    ExportRunStatus,
)
from app.exports.repositories import ExportBatchRepository
from app.exports.services import InvoiceExportService


ACTIVE_BATCH_STATUSES = {
    ExportBatchStatus.READY,
    ExportBatchStatus.RUNNING,
    ExportBatchStatus.FAILED,
}
ABANDONED_RUN_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class ExportExecutionReservation:
    batch: ExportBatchRecord
    run: ExportRunRecord
    documents: tuple[DocumentRecord, ...]
    started_at: datetime


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
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.documents = documents
        self.extractions = extractions
        self.audits = audits
        self.workflow = workflow
        self.invoice_exports = invoice_exports
        self.transactions = transactions or NoopTransactionManager()
        self._execution_lock = RLock()

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
        require_admin(context)
        documents = self.documents.list_by_workspace(context.workspace_id)
        batches = self.repository.list_batches(context.workspace_id)
        runs = self.repository.list_runs(context.workspace_id)
        document_map = {document.id: document for document in documents}
        active_membership = self._active_membership(batches)
        draft_membership = self._draft_membership(batches)
        rows = [
            self._invoice_row(
                document,
                active_batch_id=active_membership.get(document.id),
                draft_batch_id=draft_membership.get(document.id),
            )
            for document in documents
        ]
        summaries = self._summary(rows)
        normalized_view = (
            view if view in {"ready", "in_batch", "exported", "blocked", "drafts"} else "ready"
        )
        filtered = [row for row in rows if self._row_view(row) == normalized_view]
        needle = search.strip().casefold()
        vendor_filter = vendor.strip().casefold()
        currency_filter = currency.strip().casefold()
        approver_filter = approved_by.strip().casefold()
        filtered = [
            row
            for row in filtered
            if (
                not needle
                or needle
                in " ".join(
                    str(row.get(key) or "") for key in ("invoice_label", "filename", "vendor_name")
                ).casefold()
            )
            and (not vendor_filter or vendor_filter in str(row.get("vendor_name") or "").casefold())
            and (
                not currency_filter or currency_filter == str(row.get("currency") or "").casefold()
            )
            and (
                not approver_filter
                or approver_filter in str(row.get("approved_by") or "").casefold()
            )
        ]
        filtered.sort(key=lambda row: str(row["updated_at"]), reverse=True)
        total = len(filtered)
        start = (page - 1) * page_size
        selected_batch = self._selected_batch(
            context.workspace_id,
            batches,
            batch_id,
        )
        return {
            "capabilities": self.capabilities(),
            "summary": summaries,
            "items": filtered[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "filters": {
                "vendors": sorted(
                    {str(row["vendor_name"]) for row in rows if row.get("vendor_name")}
                ),
                "currencies": sorted({str(row["currency"]) for row in rows if row.get("currency")}),
                "approvers": sorted(
                    {str(row["approved_by"]) for row in rows if row.get("approved_by")}
                ),
            },
            "batch": self.batch_response(selected_batch) if selected_batch else None,
            "recent_runs": [self.run_response(run, document_map) for run in runs[:5]],
        }

    def capabilities(self) -> dict[str, object]:
        configured = self.settings.accounting_provider.strip().casefold()
        destination = (
            {
                "id": "csv_download",
                "label": "CSV download",
                "formats": ["csv"],
                "mode": "file_download",
            }
            if configured == "csv_download"
            else None
        )
        return {
            "destinations": [destination] if destination else [],
            "scheduling": False,
            "drafts": True,
            "retry": True,
            "configured_provider": configured,
            "destination_available": destination is not None,
        }

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
            accepted, rejected = self._workspace_documents(context.workspace_id, unique_ids)
            status = ExportBatchStatus.DRAFT
        else:
            accepted, rejected = self._eligible_documents(context.workspace_id, unique_ids)
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
            accepted, rejected = self._workspace_documents(
                context.workspace_id,
                unique_ids,
                exclude_batch_id=current.id,
            )
            next_status = ExportBatchStatus.DRAFT
        else:
            accepted, rejected = self._eligible_documents(
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
        require_admin(context)
        key = idempotency_key.strip()
        if not key:
            raise ValueError("Idempotency-Key is required.")
        with self._execution_lock:
            reservation = self._reserve_export_execution(context, batch_id, key)
            if isinstance(reservation, ExportRunRecord):
                return reservation
            try:
                return self._complete_export_execution(context, reservation)
            except Exception as exc:
                self._fail_export_execution(context.workspace_id, reservation)
                raise RuntimeError("Export generation failed") from exc

    def _reserve_export_execution(
        self,
        context: SecurityContext,
        batch_id: UUID,
        key: str,
    ) -> ExportExecutionReservation | ExportRunRecord:
        with self.transactions.transaction():
            existing = self.repository.get_run_by_key(context.workspace_id, key)
            if existing is not None:
                return self._reconcile_replayed_run(
                    context.workspace_id,
                    batch_id,
                    existing,
                )
            batch = self._batch(context.workspace_id, batch_id)
            documents = self._documents_for_export_execution(context, batch)
            now = datetime.now(UTC)
            run = ExportRunRecord(
                workspace_id=context.workspace_id,
                batch_id=batch.id,
                document_ids=batch.document_ids,
                idempotency_key=key,
                destination=batch.destination,
                export_format=batch.export_format,
                actor=context.actor,
                attempt_count=self._next_export_attempt(context.workspace_id, batch.id),
                created_at=now,
                updated_at=now,
            )
            reserved, created = self.repository.reserve_run(run)
            if not created:
                return self._reconcile_replayed_run(
                    context.workspace_id,
                    batch_id,
                    reserved,
                )
            self.repository.save_batch(
                replace(
                    batch,
                    status=ExportBatchStatus.RUNNING,
                    last_run_id=run.id,
                    updated_at=now,
                )
            )
            return ExportExecutionReservation(
                batch=batch,
                run=run,
                documents=documents,
                started_at=now,
            )

    def _documents_for_export_execution(
        self,
        context: SecurityContext,
        batch: ExportBatchRecord,
    ) -> tuple[DocumentRecord, ...]:
        if batch.status not in {ExportBatchStatus.READY, ExportBatchStatus.FAILED}:
            raise ExportEligibilityError(
                "Only a ready or failed batch can be executed.",
                (
                    {
                        "code": "batch_not_ready",
                        "state": "failed",
                        "label": "Batch is not ready",
                    },
                ),
            )
        checks = self.eligibility(context=context, batch=batch)
        if not all(check["state"] == "passed" for check in checks):
            raise ExportEligibilityError(
                "Export eligibility checks failed.",
                tuple(checks),
            )
        return tuple(self.documents.get(document_id) for document_id in batch.document_ids)

    def _next_export_attempt(self, workspace_id: str, batch_id: UUID) -> int:
        return 1 + max(
            (
                prior.attempt_count
                for prior in self.repository.list_runs(workspace_id)
                if prior.batch_id == batch_id
            ),
            default=0,
        )

    def _complete_export_execution(
        self,
        context: SecurityContext,
        reservation: ExportExecutionReservation,
    ) -> ExportRunRecord:
        csv_text = self.invoice_exports.render_documents_csv(list(reservation.documents))
        completed_at = datetime.now(UTC)
        succeeded = replace(
            reservation.run,
            status=ExportRunStatus.SUCCEEDED,
            file_name=(
                f"invoices-{reservation.started_at.date().isoformat()}-"
                f"{str(reservation.run.id)[:8]}.csv"
            ),
            artifact_content=csv_text,
            completed_at=completed_at,
            updated_at=completed_at,
        )
        with self.transactions.transaction():
            current_batch = self._batch(context.workspace_id, reservation.batch.id)
            current_run = self._run(context.workspace_id, reservation.run.id)
            self._require_export_ownership(current_batch, current_run)
            for document in reservation.documents:
                self.audits.add(
                    self.workflow.transition(
                        document,
                        DocumentStatus.EXPORTED,
                        context.actor,
                        payload_summary=f"export_run_id={reservation.run.id}",
                    )
                )
                self.documents.add(document)
            self.repository.save_run(succeeded)
            self.repository.save_batch(
                replace(
                    current_batch,
                    status=ExportBatchStatus.COMPLETED,
                    updated_at=completed_at,
                )
            )
        return succeeded

    def _require_export_ownership(
        self,
        batch: ExportBatchRecord,
        run: ExportRunRecord,
    ) -> None:
        if (
            run.status == ExportRunStatus.RUNNING
            and batch.status == ExportBatchStatus.RUNNING
            and batch.last_run_id == run.id
        ):
            return
        raise ExportEligibilityError(
            "This export run no longer owns the batch.",
            (
                {
                    "code": "export_run_superseded",
                    "state": "failed",
                    "label": "Export run was superseded",
                },
            ),
        )

    def _fail_export_execution(
        self,
        workspace_id: str,
        reservation: ExportExecutionReservation,
    ) -> None:
        failed_at = datetime.now(UTC)
        with self.transactions.transaction():
            current_run = self._run(workspace_id, reservation.run.id)
            if current_run.status != ExportRunStatus.RUNNING:
                return
            self.repository.save_run(
                replace(
                    current_run,
                    status=ExportRunStatus.FAILED,
                    error_code="export_generation_failed",
                    error_message="The export file could not be generated.",
                    retryable=True,
                    completed_at=failed_at,
                    updated_at=failed_at,
                )
            )
            current_batch = self._batch(workspace_id, reservation.batch.id)
            if (
                current_batch.status == ExportBatchStatus.RUNNING
                and current_batch.last_run_id == reservation.run.id
            ):
                self.repository.save_batch(
                    replace(
                        current_batch,
                        status=ExportBatchStatus.FAILED,
                        updated_at=failed_at,
                    )
                )

    def _reconcile_replayed_run(
        self,
        workspace_id: str,
        batch_id: UUID,
        run: ExportRunRecord,
    ) -> ExportRunRecord:
        if run.batch_id != batch_id:
            raise ExportIdempotencyConflict(
                "This idempotency key is already bound to another export batch."
            )
        if run.status != ExportRunStatus.RUNNING:
            return run
        batch = self._batch(workspace_id, batch_id)
        now = datetime.now(UTC)
        coherent = batch.status == ExportBatchStatus.RUNNING and batch.last_run_id == run.id
        if coherent and now - run.updated_at < ABANDONED_RUN_AFTER:
            return run
        failed = replace(
            run,
            status=ExportRunStatus.FAILED,
            error_code="export_run_abandoned",
            error_message="The previous export run did not finish.",
            retryable=True,
            completed_at=now,
            updated_at=now,
        )
        self.repository.save_run(failed)
        if coherent:
            self.repository.save_batch(
                replace(
                    batch,
                    status=ExportBatchStatus.FAILED,
                    updated_at=now,
                )
            )
        return failed

    def retry(
        self,
        *,
        context: SecurityContext,
        run_id: UUID,
        idempotency_key: str,
    ) -> ExportRunRecord:
        prior = self._run(context.workspace_id, run_id)
        if prior.status != ExportRunStatus.FAILED or not prior.retryable:
            raise ExportEligibilityError(
                "Only a retryable failed export can be retried.",
                (
                    {
                        "code": "run_not_retryable",
                        "state": "failed",
                        "label": "Run is not retryable",
                    },
                ),
            )
        return self.execute(
            context=context,
            batch_id=prior.batch_id,
            idempotency_key=idempotency_key,
        )

    def eligibility(
        self,
        *,
        context: SecurityContext,
        batch: ExportBatchRecord,
    ) -> list[dict[str, object]]:
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_map = {document.id: document for document in documents}
        selected = [document_map.get(document_id) for document_id in batch.document_ids]
        active_membership = self._active_membership(
            self.repository.list_batches(context.workspace_id),
            exclude_batch_id=batch.id,
        )
        all_present = bool(selected) and all(document is not None for document in selected)
        all_approved = all_present and all(
            document is not None and document.status == DocumentStatus.APPROVED
            for document in selected
        )
        no_blockers = all_present and all(
            not self._validation_blockers(document.id)
            for document in selected
            if document is not None
        )
        not_exported = all_present and all(
            document is not None and document.status != DocumentStatus.EXPORTED
            for document in selected
        )
        no_other_batch = all_present and all(
            document is not None and document.id not in active_membership for document in selected
        )
        destination_available = any(
            item["id"] == batch.destination and batch.export_format in item["formats"]
            for item in self.capabilities()["destinations"]
        )
        return [
            self._check(
                "all_approved",
                "All invoices approved",
                all_approved,
                "Send unapproved invoices to review.",
            ),
            self._check(
                "no_blockers",
                "No unresolved blockers",
                no_blockers,
                "Resolve invoice validation blockers.",
            ),
            self._check(
                "not_exported",
                "No invoice already exported",
                not_exported,
                "Remove previously exported invoices.",
            ),
            self._check(
                "single_active_batch",
                "No invoice in another batch",
                no_other_batch,
                "Remove invoices reserved by another batch.",
            ),
            self._check(
                "destination_available",
                "Destination is available",
                destination_available,
                "Configure a supported export destination.",
            ),
        ]

    def batch_response(self, batch: ExportBatchRecord) -> dict[str, object]:
        context = SecurityContext(
            actor=batch.created_by,
            is_admin=True,
            user_id=batch.created_by,
            workspace_id=batch.workspace_id,
            role="admin",
        )
        documents = {
            document.id: document
            for document in self.documents.list_by_workspace(batch.workspace_id)
        }
        invoices = [
            self._invoice_row(documents[document_id], active_batch_id=batch.id)
            for document_id in batch.document_ids
            if document_id in documents
        ]
        total_amount, currency = self._amount_summary(invoices)
        return {
            "id": str(batch.id),
            "name": batch.name,
            "status": batch.status.value,
            "destination": batch.destination,
            "destination_label": self._destination_label(batch.destination),
            "format": batch.export_format,
            "created_by": batch.created_by,
            "invoice_count": len(invoices),
            "total_amount": total_amount,
            "currency": currency,
            "invoices": invoices,
            "eligibility": self.eligibility(context=context, batch=batch),
            "last_run_id": str(batch.last_run_id) if batch.last_run_id else None,
            "created_at": batch.created_at.isoformat(),
            "updated_at": batch.updated_at.isoformat(),
        }

    def run_response(
        self,
        run: ExportRunRecord,
        document_map: dict[UUID, DocumentRecord] | None = None,
    ) -> dict[str, object]:
        documents = document_map or {
            document.id: document for document in self.documents.list_by_workspace(run.workspace_id)
        }
        invoice_rows = [
            self._invoice_row(documents[item]) for item in run.document_ids if item in documents
        ]
        total_amount, currency = self._amount_summary(invoice_rows)
        return {
            "id": str(run.id),
            "batch_id": str(run.batch_id),
            "status": run.status.value,
            "destination": run.destination,
            "destination_label": self._destination_label(run.destination),
            "format": run.export_format,
            "actor": run.actor,
            "invoice_count": len(run.document_ids),
            "total_amount": total_amount,
            "currency": currency,
            "attempt_count": run.attempt_count,
            "file_name": run.file_name,
            "download_available": run.status == ExportRunStatus.SUCCEEDED
            and bool(run.artifact_content),
            "error_code": run.error_code,
            "error_message": run.error_message,
            "retryable": run.retryable,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    def run_detail(self, context: SecurityContext, run_id: UUID) -> dict[str, object]:
        require_admin(context)
        run = self._run(context.workspace_id, run_id)
        response = self.run_response(run)
        response["stages"] = [
            {"label": "Validating invoices", "status": "completed"},
            {
                "label": "Generating file",
                "status": "completed" if run.status == ExportRunStatus.SUCCEEDED else "failed",
            },
            {
                "label": "Confirming result",
                "status": "completed" if run.status == ExportRunStatus.SUCCEEDED else "not_started",
            },
        ]
        return response

    def artifact(self, context: SecurityContext, run_id: UUID) -> tuple[str, str]:
        require_admin(context)
        run = self._run(context.workspace_id, run_id)
        if (
            run.status != ExportRunStatus.SUCCEEDED
            or run.artifact_content is None
            or not run.file_name
        ):
            raise ExportRunNotFound("No confirmed export artifact is available.")
        return run.file_name, run.artifact_content

    def _invoice_row(
        self,
        document: DocumentRecord,
        *,
        active_batch_id: UUID | None = None,
        draft_batch_id: UUID | None = None,
    ) -> dict[str, object]:
        stored = self._stored(document.id)
        data = stored.extraction_result.extraction.data if stored else None
        approval = next(
            (
                event
                for event in reversed(self.audits.list_for_document(document.id))
                if event.event_type == "document_approved"
            ),
            None,
        )
        blockers = self._validation_blockers(document.id)
        if document.status == DocumentStatus.EXPORTED:
            export_state = "exported"
            issue = None
        elif active_batch_id:
            export_state = "in_batch"
            issue = None
        elif draft_batch_id:
            export_state = "drafts"
            issue = None
        elif document.status == DocumentStatus.APPROVED and not blockers:
            export_state = "ready"
            issue = None
        else:
            export_state = "blocked"
            issue = (
                blockers[0]
                if blockers
                else "Waiting for approval"
                if document.status not in {DocumentStatus.REJECTED, DocumentStatus.CANCELLED}
                else "Invoice is not eligible"
            )
        invoice_number = data.invoice_number if data else None
        return {
            "id": str(document.id),
            "invoice_label": invoice_number or document.original_filename,
            "filename": document.original_filename,
            "vendor_name": data.vendor_name if data else None,
            "approved_by": approval.actor if approval else None,
            "approved_at": approval.created_at.isoformat() if approval else None,
            "total": str(data.total) if data and data.total is not None else None,
            "currency": data.currency if data else None,
            "status": export_state,
            "issue": issue,
            "batch_id": str(active_batch_id or draft_batch_id)
            if active_batch_id or draft_batch_id
            else None,
            "updated_at": document.updated_at.isoformat(),
        }

    def _summary(self, rows: list[dict[str, object]]) -> dict[str, object]:
        summary: dict[str, object] = {}
        for state in ("ready", "in_batch", "exported", "blocked"):
            state_rows = [row for row in rows if self._row_view(row) == state]
            if state == "exported":
                today = datetime.now(UTC).date()
                state_rows = [
                    row
                    for row in state_rows
                    if datetime.fromisoformat(str(row["updated_at"])).date() == today
                ]
            total_amount, currency = self._amount_summary(state_rows)
            summary[state] = {
                "count": len(state_rows),
                "amount": total_amount,
                "currency": currency,
            }
        return summary

    @staticmethod
    def _amount_summary(rows: list[dict[str, object]]) -> tuple[str | None, str | None]:
        currencies = {str(row["currency"]) for row in rows if row.get("currency")}
        if len(currencies) > 1:
            return None, None
        currency = next(iter(currencies), None)
        amount = sum(
            (Decimal(str(row["total"] or "0")) for row in rows),
            Decimal("0"),
        )
        return str(amount), currency

    @staticmethod
    def _row_view(row: dict[str, object]) -> str:
        return str(row["status"])

    def _active_membership(
        self,
        batches: list[ExportBatchRecord],
        exclude_batch_id: UUID | None = None,
    ) -> dict[UUID, UUID]:
        membership: dict[UUID, UUID] = {}
        for batch in batches:
            if batch.id == exclude_batch_id or batch.status not in ACTIVE_BATCH_STATUSES:
                continue
            for document_id in batch.document_ids:
                membership.setdefault(document_id, batch.id)
        return membership

    @staticmethod
    def _draft_membership(batches: list[ExportBatchRecord]) -> dict[UUID, UUID]:
        membership: dict[UUID, UUID] = {}
        for batch in batches:
            if batch.status != ExportBatchStatus.DRAFT:
                continue
            for document_id in batch.document_ids:
                membership.setdefault(document_id, batch.id)
        return membership

    def _selected_batch(
        self,
        workspace_id: str,
        batches: list[ExportBatchRecord],
        batch_id: UUID | None,
    ) -> ExportBatchRecord | None:
        if batch_id:
            return self._batch(workspace_id, batch_id)
        return next(
            (
                batch
                for batch in batches
                if batch.status in {ExportBatchStatus.READY, ExportBatchStatus.FAILED}
            ),
            None,
        )

    def _eligible_documents(
        self,
        workspace_id: str,
        document_ids: tuple[UUID, ...],
        exclude_batch_id: UUID | None = None,
    ) -> tuple[list[DocumentRecord], list[dict[str, str]]]:
        available = {
            document.id: document for document in self.documents.list_by_workspace(workspace_id)
        }
        active = self._active_membership(
            self.repository.list_batches(workspace_id),
            exclude_batch_id=exclude_batch_id,
        )
        accepted: list[DocumentRecord] = []
        rejected: list[dict[str, str]] = []
        for document_id in document_ids:
            document = available.get(document_id)
            reason = None
            if document is None:
                reason = "Invoice was not found in this workspace."
            elif document.status == DocumentStatus.EXPORTED:
                reason = "Invoice was already exported."
            elif document.status != DocumentStatus.APPROVED:
                reason = "Invoice is not approved."
            elif self._validation_blockers(document.id):
                reason = "Invoice has unresolved validation blockers."
            elif document.id in active:
                reason = "Invoice is already in another active export batch."
            if reason:
                rejected.append({"document_id": str(document_id), "reason": reason})
            elif document:
                accepted.append(document)
        return accepted, rejected

    def _workspace_documents(
        self,
        workspace_id: str,
        document_ids: tuple[UUID, ...],
        exclude_batch_id: UUID | None = None,
    ) -> tuple[list[DocumentRecord], list[dict[str, str]]]:
        available = {
            document.id: document for document in self.documents.list_by_workspace(workspace_id)
        }
        active = self._active_membership(
            self.repository.list_batches(workspace_id),
            exclude_batch_id=exclude_batch_id,
        )
        accepted: list[DocumentRecord] = []
        rejected: list[dict[str, str]] = []
        for document_id in document_ids:
            document = available.get(document_id)
            reason = None
            if document is None:
                reason = "Invoice was not found in this workspace."
            elif document.status == DocumentStatus.EXPORTED:
                reason = "Invoice was already exported."
            elif document.id in active:
                reason = "Invoice is already in another active export batch."
            if reason:
                rejected.append({"document_id": str(document_id), "reason": reason})
            elif document:
                accepted.append(document)
        return accepted, rejected

    def _validation_blockers(self, document_id: UUID) -> list[str]:
        stored = self._stored(document_id)
        if stored is None:
            return ["Invoice data has not been extracted"]
        return [
            issue.message.replace("_", " ")
            for issue in stored.validation_report.issues
            if issue.severity.value == "error"
        ]

    def _stored(self, document_id: UUID) -> StoredExtraction | None:
        try:
            return self.extractions.get_for_document(document_id)
        except NotFoundError:
            return None

    def _batch(self, workspace_id: str, batch_id: UUID) -> ExportBatchRecord:
        batch = self.repository.get_batch(workspace_id, batch_id)
        if batch is None:
            raise ExportBatchNotFound("Export batch not found.")
        return batch

    def _run(self, workspace_id: str, run_id: UUID) -> ExportRunRecord:
        run = self.repository.get_run(workspace_id, run_id)
        if run is None:
            raise ExportRunNotFound("Export run not found.")
        return run

    def _require_destination(self) -> dict[str, object]:
        destinations = self.capabilities()["destinations"]
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

    def _destination_label(self, destination: str) -> str:
        return next(
            (
                str(item["label"])
                for item in self.capabilities()["destinations"]
                if item["id"] == destination
            ),
            destination.replace("_", " ").title(),
        )

    @staticmethod
    def _check(code: str, label: str, passed: bool, failure: str) -> dict[str, object]:
        return {
            "code": code,
            "label": label,
            "state": "passed" if passed else "failed",
            "detail": "Verified from current records." if passed else failure,
        }
