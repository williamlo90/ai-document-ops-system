from __future__ import annotations

from app.documents.worker import DocumentProcessingWorker


def run_until_empty(worker: DocumentProcessingWorker, max_jobs: int = 100) -> int:
    processed = 0
    while processed < max_jobs and worker.run_once():
        processed += 1
    return processed
