from __future__ import annotations

from app.core.security import SecurityContext, require_admin
from app.documents.jobs import ProcessingJobStatus
from app.documents.status import DocumentStatus
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    JobRepository,
)
from app.metrics.queries import MetricsQueryRepository, MetricsSnapshot


ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD = 0.05


class MetricsService:
    def __init__(
        self,
        documents: DocumentRepository,
        jobs: JobRepository,
        audits: AuditRepository,
        queries: MetricsQueryRepository | None = None,
    ) -> None:
        self.documents = documents
        self.jobs = jobs
        self.audits = audits
        self.queries = queries

    def summary(self, context: SecurityContext) -> dict[str, object]:
        require_admin(context)
        if self.queries is not None:
            return self._snapshot_summary(self.queries.summary(context.workspace_id))
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_ids = {document.id for document in documents}
        by_status: dict[str, int] = {}
        for document in documents:
            by_status[document.status.value] = by_status.get(document.status.value, 0) + 1
        jobs = [job for job in self.jobs.list_all() if job.document_id in document_ids]
        audit_events = [
            event
            for document_id in document_ids
            for event in self.audits.list_for_document(document_id)
        ]
        succeeded_jobs = [job for job in jobs if job.status == ProcessingJobStatus.SUCCEEDED]
        return {
            "documents_total": len(documents),
            "jobs_total": len(jobs),
            "audit_events_total": len(audit_events),
            "by_status": by_status,
            "queue": self._queue_metrics(jobs),
            "provider": self._provider_metrics(jobs),
            "review": self._review_metrics(by_status, audit_events),
            "cost": self._cost_metrics(succeeded_jobs),
            "average_processing_time_ms": self._average_processing_time_ms(jobs),
        }

    @staticmethod
    def _snapshot_summary(snapshot: MetricsSnapshot) -> dict[str, object]:
        estimated_total = snapshot.succeeded_jobs * ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD
        return {
            "documents_total": snapshot.documents_total,
            "jobs_total": snapshot.jobs_total,
            "audit_events_total": snapshot.audit_events_total,
            "by_status": snapshot.by_status,
            "queue": snapshot.queue,
            "provider": {
                "failure_count": snapshot.provider_failures,
                "retrying_count": snapshot.queue["retrying"],
                "dead_letter_count": snapshot.queue["dead_letter"],
                "by_provider": snapshot.provider_runs,
            },
            "review": {
                "queue_count": snapshot.by_status.get(DocumentStatus.NEEDS_REVIEW.value, 0),
                "approved_count": snapshot.by_status.get(DocumentStatus.APPROVED.value, 0),
                "rejected_count": snapshot.by_status.get(DocumentStatus.REJECTED.value, 0),
                "correction_count": snapshot.correction_count,
                "review_saved_count": snapshot.review_saved_count,
            },
            "cost": {
                "processed_documents": snapshot.succeeded_jobs,
                "estimated_cost_per_document_usd": ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD,
                "estimated_total_usd": round(estimated_total, 6),
            },
            "average_processing_time_ms": snapshot.average_processing_time_ms,
        }

    def _queue_metrics(self, jobs: list) -> dict[str, int]:
        return {
            "queued": self._job_count(jobs, ProcessingJobStatus.QUEUED),
            "running": self._job_count(jobs, ProcessingJobStatus.RUNNING),
            "retrying": self._job_count(jobs, ProcessingJobStatus.RETRYING),
            "failed": self._job_count(jobs, ProcessingJobStatus.FAILED),
            "dead_letter": self._job_count(jobs, ProcessingJobStatus.DEAD_LETTER),
            "succeeded": self._job_count(jobs, ProcessingJobStatus.SUCCEEDED),
        }

    def _provider_metrics(self, jobs: list) -> dict[str, object]:
        failures = [
            job
            for job in jobs
            if job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTER}
        ]
        by_provider: dict[str, int] = {}
        for job in jobs:
            if not job.provider_name:
                continue
            by_provider[job.provider_name] = by_provider.get(job.provider_name, 0) + 1
        return {
            "failure_count": len(failures),
            "retrying_count": self._job_count(jobs, ProcessingJobStatus.RETRYING),
            "dead_letter_count": self._job_count(jobs, ProcessingJobStatus.DEAD_LETTER),
            "by_provider": by_provider,
        }

    def _review_metrics(self, by_status: dict[str, int], audit_events: list) -> dict[str, int]:
        return {
            "queue_count": by_status.get(DocumentStatus.NEEDS_REVIEW.value, 0),
            "approved_count": by_status.get(DocumentStatus.APPROVED.value, 0),
            "rejected_count": by_status.get(DocumentStatus.REJECTED.value, 0),
            "correction_count": self._event_count(audit_events, "extraction_updated"),
            "review_saved_count": self._event_count(audit_events, "review_saved"),
        }

    def _cost_metrics(self, succeeded_jobs: list) -> dict[str, float | int]:
        estimated_total = len(succeeded_jobs) * ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD
        return {
            "processed_documents": len(succeeded_jobs),
            "estimated_cost_per_document_usd": ESTIMATED_COST_PER_SUCCEEDED_DOCUMENT_USD,
            "estimated_total_usd": round(estimated_total, 6),
        }

    def _average_processing_time_ms(self, jobs: list) -> float:
        durations: list[float] = []
        for job in jobs:
            if job.status != ProcessingJobStatus.SUCCEEDED:
                continue
            if job.started_at is None or job.finished_at is None:
                continue
            delta = (job.finished_at - job.started_at).total_seconds()
            if delta < 0:
                continue
            durations.append(delta * 1000)
        if not durations:
            return 0.0
        return float(round(sum(durations) / len(durations)))

    def _job_count(self, jobs: list, status: ProcessingJobStatus) -> int:
        return sum(1 for job in jobs if job.status == status)

    def _event_count(self, audit_events: list, event_type: str) -> int:
        return sum(1 for event in audit_events if event.event_type == event_type)
