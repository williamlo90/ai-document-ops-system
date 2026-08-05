from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from app.core.security import SecurityContext
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
    StoredExtraction,
)
from app.documents.status import DocumentStatus
from app.exports.models import ExportBatchRecord, ExportBatchStatus
from app.exports.repositories import ExportBatchRepository


ACTIVE_BATCH_STATUSES = {
    ExportBatchStatus.READY,
    ExportBatchStatus.RUNNING,
    ExportBatchStatus.FAILED,
}


class ExportDestination(TypedDict):
    id: str
    label: str
    formats: list[str]
    mode: str


class ExportEligibilityPolicy:
    def __init__(
        self,
        *,
        repository: ExportBatchRepository,
        documents: DocumentRepository,
        extractions: ExtractionRepository,
    ) -> None:
        self.repository = repository
        self.documents = documents
        self.extractions = extractions

    def checks(
        self,
        *,
        context: SecurityContext,
        batch: ExportBatchRecord,
        destinations: list[ExportDestination],
    ) -> list[dict[str, object]]:
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_map = {document.id: document for document in documents}
        selected = [document_map.get(document_id) for document_id in batch.document_ids]
        active_membership = self.active_membership(
            self.repository.list_batches(context.workspace_id),
            exclude_batch_id=batch.id,
        )
        document_checks = self._document_checks(selected, active_membership)
        destination_available = self._destination_available(
            batch.destination,
            batch.export_format,
            destinations,
        )
        return [
            self._check(
                "all_approved",
                "All invoices approved",
                document_checks["all_approved"],
                "Send unapproved invoices to review.",
            ),
            self._check(
                "no_blockers",
                "No unresolved blockers",
                document_checks["no_blockers"],
                "Resolve invoice validation blockers.",
            ),
            self._check(
                "not_exported",
                "No invoice already exported",
                document_checks["not_exported"],
                "Remove previously exported invoices.",
            ),
            self._check(
                "single_active_batch",
                "No invoice in another batch",
                document_checks["no_other_batch"],
                "Remove invoices reserved by another batch.",
            ),
            self._check(
                "destination_available",
                "Destination is available",
                destination_available,
                "Configure a supported export destination.",
            ),
        ]

    def _document_checks(
        self,
        selected: list[DocumentRecord | None],
        active_membership: dict[UUID, UUID],
    ) -> dict[str, bool]:
        all_present = bool(selected) and all(document is not None for document in selected)
        present = [document for document in selected if document is not None]
        return {
            "all_approved": all_present
            and all(document.status == DocumentStatus.APPROVED for document in present),
            "no_blockers": all_present
            and all(not self.validation_blockers(document.id) for document in present),
            "not_exported": all_present
            and all(document.status != DocumentStatus.EXPORTED for document in present),
            "no_other_batch": all_present
            and all(document.id not in active_membership for document in present),
        }

    @staticmethod
    def _destination_available(
        destination: str,
        export_format: str,
        destinations: list[ExportDestination],
    ) -> bool:
        return any(
            item["id"] == destination and export_format in item["formats"] for item in destinations
        )

    def eligible_documents(
        self,
        workspace_id: str,
        document_ids: tuple[UUID, ...],
        exclude_batch_id: UUID | None = None,
    ) -> tuple[list[DocumentRecord], list[dict[str, str]]]:
        available = {
            document.id: document for document in self.documents.list_by_workspace(workspace_id)
        }
        active = self.active_membership(
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
            elif self.validation_blockers(document.id):
                reason = "Invoice has unresolved validation blockers."
            elif document.id in active:
                reason = "Invoice is already in another active export batch."
            if reason:
                rejected.append({"document_id": str(document_id), "reason": reason})
            elif document:
                accepted.append(document)
        return accepted, rejected

    def workspace_documents(
        self,
        workspace_id: str,
        document_ids: tuple[UUID, ...],
        exclude_batch_id: UUID | None = None,
    ) -> tuple[list[DocumentRecord], list[dict[str, str]]]:
        available = {
            document.id: document for document in self.documents.list_by_workspace(workspace_id)
        }
        active = self.active_membership(
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

    @staticmethod
    def active_membership(
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

    def validation_blockers(self, document_id: UUID) -> list[str]:
        stored = self.stored(document_id)
        if stored is None:
            return ["Invoice data has not been extracted"]
        return [
            issue.message.replace("_", " ")
            for issue in stored.validation_report.issues
            if issue.severity.value == "error"
        ]

    def stored(self, document_id: UUID) -> StoredExtraction | None:
        try:
            return self.extractions.get_for_document(document_id)
        except NotFoundError:
            return None

    @staticmethod
    def _check(code: str, label: str, passed: bool, failure: str) -> dict[str, object]:
        return {
            "code": code,
            "label": label,
            "state": "passed" if passed else "failed",
            "detail": "Verified from current records." if passed else failure,
        }
