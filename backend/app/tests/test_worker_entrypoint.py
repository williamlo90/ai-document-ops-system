from __future__ import annotations

from contextlib import contextmanager
import unittest
from typing import Iterator

from app.documents.jobs import JobStatus, ProcessingJob, StaleLeaseError
from app.documents.repositories import InMemoryAuditRepository, InMemoryDocumentRepository, InMemoryJobRepository, InMemoryTransactionManager
from app.documents.worker import DocumentProcessingWorker, HandlerFailure
from uuid import uuid4


class RecordingHandler:
    def __init__(self, transactions: "ObservedTransactions", failure: HandlerFailure | None = None) -> None:
        self.transactions = transactions
        self.failure = failure

    def handle(self, document_id) -> None:
        if self.transactions.active:
            raise AssertionError("provider handler ran inside write transaction")
        if self.failure:
            raise self.failure


class ObservedTransactions:
    def __init__(self, delegate: InMemoryTransactionManager) -> None:
        self.delegate = delegate
        self.active = False

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.delegate.transaction():
            self.active = True
            try:
                yield
            finally:
                self.active = False


class WorkerEntrypointTests(unittest.TestCase):
    def test_handler_runs_outside_transaction_and_completion_is_fenced(self) -> None:
        documents = InMemoryDocumentRepository()
        audits = InMemoryAuditRepository()
        jobs = InMemoryJobRepository()
        observed = ObservedTransactions(InMemoryTransactionManager(documents, audits, jobs))
        job = ProcessingJob(uuid4())
        jobs.add(job)
        self.assertTrue(DocumentProcessingWorker(jobs, observed, RecordingHandler(observed)).run_once())
        self.assertEqual(jobs.get(job.id).status, JobStatus.COMPLETED)  # type: ignore[union-attr]
        with self.assertRaises(StaleLeaseError):
            stale = jobs.get(job.id)
            assert stale is not None
            stale.complete("old-token")

    def test_retryable_and_terminal_failures_remain_distinct(self) -> None:
        for retryable, expected in ((True, JobStatus.RETRY), (False, JobStatus.FAILED)):
            with self.subTest(retryable=retryable):
                documents = InMemoryDocumentRepository()
                audits = InMemoryAuditRepository()
                jobs = InMemoryJobRepository()
                observed = ObservedTransactions(InMemoryTransactionManager(documents, audits, jobs))
                job = ProcessingJob(uuid4())
                jobs.add(job)
                handler = RecordingHandler(observed, HandlerFailure("provider-error", retryable=retryable))
                DocumentProcessingWorker(jobs, observed, handler).run_once()
                self.assertEqual(jobs.get(job.id).status, expected)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
