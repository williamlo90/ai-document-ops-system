from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import Settings
from app.core.transactions import TransactionManager
from app.documents.repositories import InMemoryAuditRepository, InMemoryDocumentRepository, InMemoryJobRepository, InMemoryTransactionManager
from app.documents.sqlite_repositories import SqliteAuditRepository, SqliteDocumentRepository, SqliteJobRepository
from app.documents.sqlite_store import SqliteStore
from app.review.repositories import InMemoryCorrectionRepository, InMemoryReviewRepository
from app.review.sqlite_repositories import SqliteCorrectionRepository, SqliteReviewRepository


DocumentRepository = InMemoryDocumentRepository | SqliteDocumentRepository
AuditRepository = InMemoryAuditRepository | SqliteAuditRepository
JobRepository = InMemoryJobRepository | SqliteJobRepository
ReviewRepository = InMemoryReviewRepository | SqliteReviewRepository
CorrectionRepository = InMemoryCorrectionRepository | SqliteCorrectionRepository


@dataclass(slots=True)
class PersistenceModule:
    documents: DocumentRepository
    audits: AuditRepository
    jobs: JobRepository
    reviews: ReviewRepository
    corrections: CorrectionRepository
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
            reviews=SqliteReviewRepository(store),
            corrections=SqliteCorrectionRepository(store),
            transactions=store,
            store=store,
        )
    documents = InMemoryDocumentRepository()
    audits = InMemoryAuditRepository()
    jobs = InMemoryJobRepository()
    reviews = InMemoryReviewRepository()
    corrections = InMemoryCorrectionRepository()
    return PersistenceModule(
        documents=documents,
        audits=audits,
        jobs=jobs,
        reviews=reviews,
        corrections=corrections,
        transactions=InMemoryTransactionManager(documents, audits, jobs),
    )
