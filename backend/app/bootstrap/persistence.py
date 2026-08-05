from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import Settings
from app.core.transactions import TransactionManager
from app.documents.repositories import InMemoryAuditRepository, InMemoryDocumentRepository, InMemoryJobRepository, InMemoryTransactionManager
from app.documents.sqlite_repositories import SqliteAuditRepository, SqliteDocumentRepository, SqliteJobRepository
from app.documents.sqlite_store import SqliteStore


DocumentRepository = InMemoryDocumentRepository | SqliteDocumentRepository
AuditRepository = InMemoryAuditRepository | SqliteAuditRepository
JobRepository = InMemoryJobRepository | SqliteJobRepository


@dataclass(slots=True)
class PersistenceModule:
    documents: DocumentRepository
    audits: AuditRepository
    jobs: JobRepository
    transactions: TransactionManager
    store: SqliteStore | None = None

    def close(self) -> None:
        if self.store is not None:
            self.store.close()


def build_persistence_module(settings: Settings) -> PersistenceModule:
    if settings.persistence_backend == "sqlite":
        store = SqliteStore(settings.sqlite_path)
        return PersistenceModule(
            documents=SqliteDocumentRepository(store),
            audits=SqliteAuditRepository(store),
            jobs=SqliteJobRepository(store),
            transactions=store,
            store=store,
        )
    documents = InMemoryDocumentRepository()
    audits = InMemoryAuditRepository()
    jobs = InMemoryJobRepository()
    return PersistenceModule(
        documents=documents,
        audits=audits,
        jobs=jobs,
        transactions=InMemoryTransactionManager(documents, audits, jobs),
    )
