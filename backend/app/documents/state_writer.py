from __future__ import annotations

from uuid import UUID

from app.core.transactions import NoopTransactionManager, TransactionManager
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import AuditRepository, DocumentRepository, NotFoundError
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService


class DocumentStateWriter:
    """Persist a document transition and its audit event as one operation."""

    def __init__(
        self,
        documents: DocumentRepository,
        audits: AuditRepository,
        workflow: DocumentWorkflowService,
        transactions: TransactionManager | None = None,
    ) -> None:
        self.documents = documents
        self.audits = audits
        self.workflow = workflow
        self.transactions = transactions or NoopTransactionManager()

    def transition(
        self,
        document: DocumentRecord,
        target_status: DocumentStatus,
        actor: str,
        payload_summary: str | None = None,
    ) -> AuditEvent:
        with self.transactions.transaction():
            return self._transition(
                document,
                target_status,
                actor,
                payload_summary,
            )

    def transition_many_by_id(
        self,
        document_ids: tuple[UUID, ...],
        workspace_id: str,
        target_status: DocumentStatus,
        actor: str,
        payload_summary: str | None = None,
    ) -> list[DocumentRecord]:
        transitioned: list[DocumentRecord] = []
        with self.transactions.transaction():
            for document_id in document_ids:
                document = self._workspace_document(document_id, workspace_id)
                self._transition(document, target_status, actor, payload_summary)
                transitioned.append(document)
        return transitioned

    def _workspace_document(self, document_id: UUID, workspace_id: str) -> DocumentRecord:
        document = self.documents.get(document_id)
        if document.workspace_id != workspace_id:
            raise NotFoundError(f"Document not found: {document_id}")
        return document

    def _transition(
        self,
        document: DocumentRecord,
        target_status: DocumentStatus,
        actor: str,
        payload_summary: str | None,
    ) -> AuditEvent:
        event = self.workflow.transition(
            document,
            target_status,
            actor,
            payload_summary=payload_summary,
        )
        self.audits.add(event)
        self.documents.save(document)
        return event
