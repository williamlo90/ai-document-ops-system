from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.security import SecurityContext, require_admin
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.documents.repositories import AuditRepository, DocumentRepository
from app.documents.status import DocumentStatus
from app.exports.eligibility import ExportDestination, ExportEligibilityPolicy
from app.exports.models import (
    ExportBatchNotFound,
    ExportBatchRecord,
    ExportBatchStatus,
    ExportRunNotFound,
    ExportRunRecord,
    ExportRunStatus,
)
from app.exports.repositories import ExportBatchRepository


class ExportWorkspaceQuery:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: ExportBatchRepository,
        documents: DocumentRepository,
        audits: AuditRepository,
        eligibility: ExportEligibilityPolicy,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.documents = documents
        self.audits = audits
        self.eligibility = eligibility

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
        rows = self._workspace_rows(documents, batches)
        filtered = self._filtered_rows(
            rows,
            view=view,
            search=search,
            vendor=vendor,
            currency=currency,
            approved_by=approved_by,
        )
        total = len(filtered)
        start = (page - 1) * page_size
        selected_batch = self._selected_batch(context.workspace_id, batches, batch_id)
        return {
            "capabilities": self.capabilities(),
            "summary": self._summary(rows),
            "items": filtered[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "filters": self._filter_options(rows),
            "batch": self.batch_response(selected_batch) if selected_batch else None,
            "recent_runs": [self.run_response(run, document_map) for run in runs[:5]],
        }

    def _workspace_rows(
        self,
        documents: list[DocumentRecord],
        batches: list[ExportBatchRecord],
    ) -> list[dict[str, object]]:
        active_membership = self.eligibility.active_membership(batches)
        draft_membership = self._draft_membership(batches)
        return [
            self._invoice_row(
                document,
                active_batch_id=active_membership.get(document.id),
                draft_batch_id=draft_membership.get(document.id),
            )
            for document in documents
        ]

    def _filtered_rows(
        self,
        rows: list[dict[str, object]],
        *,
        view: str,
        search: str,
        vendor: str,
        currency: str,
        approved_by: str,
    ) -> list[dict[str, object]]:
        normalized_view = self._normalized_view(view)
        filtered = [row for row in rows if self._row_view(row) == normalized_view]
        needle = search.strip().casefold()
        vendor_filter = vendor.strip().casefold()
        currency_filter = currency.strip().casefold()
        approver_filter = approved_by.strip().casefold()
        matching = [
            row
            for row in filtered
            if self._matches_filters(
                row,
                needle=needle,
                vendor=vendor_filter,
                currency=currency_filter,
                approver=approver_filter,
            )
        ]
        matching.sort(key=lambda row: str(row["updated_at"]), reverse=True)
        return matching

    @staticmethod
    def _normalized_view(view: str) -> str:
        supported = {"ready", "in_batch", "exported", "blocked", "drafts"}
        return view if view in supported else "ready"

    @staticmethod
    def _matches_filters(
        row: dict[str, object],
        *,
        needle: str,
        vendor: str,
        currency: str,
        approver: str,
    ) -> bool:
        searchable = " ".join(
            str(row.get(key) or "") for key in ("invoice_label", "filename", "vendor_name")
        ).casefold()
        return all(
            (
                not needle or needle in searchable,
                not vendor or vendor in str(row.get("vendor_name") or "").casefold(),
                not currency or currency == str(row.get("currency") or "").casefold(),
                not approver or approver in str(row.get("approved_by") or "").casefold(),
            )
        )

    @staticmethod
    def _filter_options(rows: list[dict[str, object]]) -> dict[str, list[str]]:
        return {
            "vendors": sorted({str(row["vendor_name"]) for row in rows if row.get("vendor_name")}),
            "currencies": sorted({str(row["currency"]) for row in rows if row.get("currency")}),
            "approvers": sorted(
                {str(row["approved_by"]) for row in rows if row.get("approved_by")}
            ),
        }

    def capabilities(self) -> dict[str, object]:
        configured = self.settings.accounting_provider.strip().casefold()
        destination: ExportDestination | None = (
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

    def destinations(self) -> list[ExportDestination]:
        configured = self.settings.accounting_provider.strip().casefold()
        if configured != "csv_download":
            return []
        return [
            {
                "id": "csv_download",
                "label": "CSV download",
                "formats": ["csv"],
                "mode": "file_download",
            }
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
            "destination_label": self.destination_label(batch.destination),
            "format": batch.export_format,
            "created_by": batch.created_by,
            "invoice_count": len(invoices),
            "total_amount": total_amount,
            "currency": currency,
            "invoices": invoices,
            "eligibility": self.eligibility.checks(
                context=context,
                batch=batch,
                destinations=self.destinations(),
            ),
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
            "destination_label": self.destination_label(run.destination),
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

    def destination_label(self, destination: str) -> str:
        return next(
            (str(item["label"]) for item in self.destinations() if item["id"] == destination),
            destination.replace("_", " ").title(),
        )

    def _invoice_row(
        self,
        document: DocumentRecord,
        *,
        active_batch_id: UUID | None = None,
        draft_batch_id: UUID | None = None,
    ) -> dict[str, object]:
        stored = self.eligibility.stored(document.id)
        data = stored.extraction_result.extraction.data if stored else None
        approval = next(
            (
                event
                for event in reversed(self.audits.list_for_document(document.id))
                if event.event_type == "document_approved"
            ),
            None,
        )
        blockers = self.eligibility.validation_blockers(document.id)
        export_state, issue = self._export_state(
            document,
            blockers,
            active_batch_id=active_batch_id,
            draft_batch_id=draft_batch_id,
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

    @staticmethod
    def _export_state(
        document: DocumentRecord,
        blockers: list[str],
        *,
        active_batch_id: UUID | None,
        draft_batch_id: UUID | None,
    ) -> tuple[str, str | None]:
        if document.status == DocumentStatus.EXPORTED:
            return "exported", None
        if active_batch_id:
            return "in_batch", None
        if draft_batch_id:
            return "drafts", None
        if document.status == DocumentStatus.APPROVED and not blockers:
            return "ready", None
        if blockers:
            return "blocked", blockers[0]
        if document.status in {DocumentStatus.REJECTED, DocumentStatus.CANCELLED}:
            return "blocked", "Invoice is not eligible"
        return "blocked", "Waiting for approval"

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
