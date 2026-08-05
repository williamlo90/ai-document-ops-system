from __future__ import annotations

from typing import Protocol

from app.core.transactions import TransactionManager
from app.documents.models import AuditEvent, DocumentRecord


class DocumentWriter(Protocol):
    def save(self, document: DocumentRecord) -> None: ...


class AuditWriter(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class DocumentStateWriter:
    def __init__(self, documents: DocumentWriter, audits: AuditWriter, transactions: TransactionManager) -> None:
        self.documents = documents
        self.audits = audits
        self.transactions = transactions

    def save_with_audit(self, document: DocumentRecord, event: AuditEvent) -> None:
        with self.transactions.transaction():
            self.documents.save(document)
            self.audits.append(event)
