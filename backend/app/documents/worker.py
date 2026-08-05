from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.core.transactions import TransactionManager
from app.documents.jobs import ProcessingJob


class JobRepository(Protocol):
    def next_claimable(self) -> ProcessingJob | None: ...
    def get(self, job_id: UUID) -> ProcessingJob | None: ...
    def save(self, job: ProcessingJob) -> None: ...


class JobHandler(Protocol):
    def handle(self, document_id: UUID) -> None: ...


class HandlerFailure(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class DocumentProcessingWorker:
    def __init__(self, jobs: JobRepository, transactions: TransactionManager, handler: JobHandler) -> None:
        self.jobs = jobs
        self.transactions = transactions
        self.handler = handler

    def run_once(self) -> bool:
        with self.transactions.transaction():
            job = self.jobs.next_claimable()
            if job is None:
                return False
            token = job.claim(60)
            self.jobs.save(job)

        try:
            self.handler.handle(job.document_id)
        except HandlerFailure as exc:
            with self.transactions.transaction():
                current = self._required_job(job.id)
                current.fail(token, retryable=exc.retryable, error_code=exc.code)
                self.jobs.save(current)
            return True

        with self.transactions.transaction():
            current = self._required_job(job.id)
            current.complete(token)
            self.jobs.save(current)
        return True

    def _required_job(self, job_id: UUID) -> ProcessingJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job
