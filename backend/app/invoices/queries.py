from __future__ import annotations

from typing import Protocol

from app.documents.models import DocumentRecord


class WorkspaceDocuments(Protocol):
    def list_by_workspace(self, workspace_id: str) -> list[DocumentRecord]: ...


class InvoiceQueries:
    def __init__(self, documents: WorkspaceDocuments) -> None:
        self.documents = documents

    def list_for_workspace(self, workspace_id: str) -> list[dict[str, object]]:
        return [
            {
                "id": str(document.id),
                "filename": document.original_filename,
                "status": document.status.value,
                "updated_at": document.updated_at.isoformat(),
            }
            for document in self.documents.list_by_workspace(workspace_id)
        ]
