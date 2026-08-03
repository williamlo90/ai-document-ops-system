from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.transactions import TransactionManager
from app.documents.models import DocumentRecord
from app.documents.repositories import DocumentRepository
from app.documents.state_writer import DocumentStateWriter
from app.documents.status import DocumentStatus
from app.exports.eligibility import ExportDestination, ExportEligibilityPolicy
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


ABANDONED_RUN_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class ExportExecutionReservation:
    batch: ExportBatchRecord
    run: ExportRunRecord
    documents: tuple[DocumentRecord, ...]
    started_at: datetime


class ExportExecutionLifecycle:
    def __init__(
        self,
        *,
        repository: ExportBatchRepository,
        documents: DocumentRepository,
        state_writer: DocumentStateWriter,
        invoice_exports: InvoiceExportService,
        transactions: TransactionManager,
        eligibility: ExportEligibilityPolicy,
        destinations: Callable[[], list[ExportDestination]],
    ) -> None:
        self.repository = repository
        self.documents = documents
        self.state_writer = state_writer
        self.invoice_exports = invoice_exports
        self.transactions = transactions
        self.eligibility = eligibility
        self.destinations = destinations
        self._execution_lock = RLock()

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
            reservation = self._reserve(context, batch_id, key)
            if isinstance(reservation, ExportRunRecord):
                return reservation
            try:
                return self._complete(context, reservation)
            except Exception as exc:
                self._fail(context.workspace_id, reservation)
                raise RuntimeError("Export generation failed") from exc

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

    def _reserve(
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
            documents = self._documents_for_execution(context, batch)
            now = datetime.now(UTC)
            run = ExportRunRecord(
                workspace_id=context.workspace_id,
                batch_id=batch.id,
                document_ids=batch.document_ids,
                idempotency_key=key,
                destination=batch.destination,
                export_format=batch.export_format,
                actor=context.actor,
                attempt_count=self._next_attempt(context.workspace_id, batch.id),
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

    def _documents_for_execution(
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
        checks = self.eligibility.checks(
            context=context,
            batch=batch,
            destinations=self.destinations(),
        )
        if not all(check["state"] == "passed" for check in checks):
            raise ExportEligibilityError(
                "Export eligibility checks failed.",
                tuple(checks),
            )
        return tuple(self.documents.get(document_id) for document_id in batch.document_ids)

    def _next_attempt(self, workspace_id: str, batch_id: UUID) -> int:
        return 1 + max(
            (
                prior.attempt_count
                for prior in self.repository.list_runs(workspace_id)
                if prior.batch_id == batch_id
            ),
            default=0,
        )

    def _complete(
        self,
        context: SecurityContext,
        reservation: ExportExecutionReservation,
    ) -> ExportRunRecord:
        csv_text = self.invoice_exports.render_document_ids_csv(
            tuple(document.id for document in reservation.documents)
        )
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
            self._require_ownership(current_batch, current_run)
            self.state_writer.transition_many_by_id(
                reservation.run.document_ids,
                context.workspace_id,
                DocumentStatus.EXPORTED,
                context.actor,
                payload_summary=f"export_run_id={reservation.run.id}",
            )
            self.repository.save_run(succeeded)
            self.repository.save_batch(
                replace(
                    current_batch,
                    status=ExportBatchStatus.COMPLETED,
                    updated_at=completed_at,
                )
            )
        return succeeded

    @staticmethod
    def _require_ownership(
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

    def _fail(
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
