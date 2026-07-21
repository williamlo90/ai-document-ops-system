from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable

from app.core.security import SecurityContext, require_admin
from app.core.settings import Settings
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    JobRepository,
    NotFoundError,
)
from app.documents.status import DocumentStatus
from app.exports.models import ExportRunRecord, ExportRunStatus
from app.exports.repositories import ExportBatchRepository


ACTIVE_JOB_STATES = {ProcessingJobStatus.RUNNING}
WAITING_JOB_STATES = {ProcessingJobStatus.QUEUED, ProcessingJobStatus.RETRYING}
FAILED_JOB_STATES = {ProcessingJobStatus.FAILED, ProcessingJobStatus.DEAD_LETTER}


@dataclass
class SystemDashboardService:
    settings: Settings
    documents: DocumentRepository
    jobs: JobRepository
    audits: AuditRepository
    extractions: ExtractionRepository
    export_batches: ExportBatchRepository

    def dashboard(
        self,
        context: SecurityContext,
        *,
        readiness: dict[str, bool],
        now: datetime | None = None,
    ) -> dict[str, object]:
        require_admin(context)
        observed_at = now or datetime.now(UTC)
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_map = {document.id: document for document in documents}
        jobs = [job for job in self.jobs.list_all() if job.document_id in document_map]
        events = [
            event for document in documents for event in self.audits.list_for_document(document.id)
        ]
        export_runs = self.export_batches.list_runs(context.workspace_id)
        services = self._services(
            readiness=readiness,
            documents=documents,
            jobs=jobs,
            export_runs=export_runs,
            observed_at=observed_at,
        )
        alerts = self._alerts(services, jobs, document_map)
        recent_jobs = self._recent_jobs(jobs, document_map)
        return {
            "observed_at": observed_at.isoformat(),
            "freshness": {
                "state": "current",
                "label": "Observed when this page was refreshed",
            },
            "overall": self._overall(services),
            "kpis": {
                "processing_now": sum(job.status in ACTIVE_JOB_STATES for job in jobs),
                "waiting": sum(job.status in WAITING_JOB_STATES for job in jobs),
                "completed_today": sum(
                    job.status == ProcessingJobStatus.SUCCEEDED
                    and job.finished_at is not None
                    and job.finished_at.astimezone(UTC).date() == observed_at.astimezone(UTC).date()
                    for job in jobs
                ),
                "needs_attention": len(alerts),
            },
            "services": services,
            "alerts": alerts,
            "flow": self._flow(
                documents=documents,
                events=events,
                export_runs=export_runs,
                observed_at=observed_at,
            ),
            "recent_jobs": recent_jobs,
            "integrations": self._integrations(services),
            "audit": self._audit(events, document_map),
            "maintenance": {
                "scheduled": False,
                "title": "No maintenance scheduled",
                "detail": "This application does not currently manage a maintenance calendar.",
            },
        }

    def _services(
        self,
        *,
        readiness: dict[str, bool],
        documents: list[DocumentRecord],
        jobs: list[ProcessingJob],
        export_runs: list[ExportRunRecord],
        observed_at: datetime,
    ) -> list[dict[str, object]]:
        storage_ready = bool(readiness.get("storage"))
        database_ready = bool(readiness.get("database"))
        return [
            self._current_service(
                service_id="uploads",
                name="Invoice uploads",
                status="operational" if storage_ready and database_ready else "unavailable",
                observed_at=observed_at,
                activity=f"{len(documents)} invoices stored",
                evidence=(
                    "Database and private document storage checks passed."
                    if storage_ready and database_ready
                    else "A required upload dependency did not pass its current readiness check."
                ),
                affected="New invoice uploads" if not storage_ready or not database_ready else None,
            ),
            self._provider_service(
                service_id="reader",
                name="Document reader",
                configured=self.settings.parser_provider,
                runtime_name="mistral_ocr",
                jobs=jobs,
                observed_at=observed_at,
            ),
            self._provider_service(
                service_id="extractor",
                name="Data extractor",
                configured=self.settings.extractor_provider,
                runtime_name="llm_json",
                jobs=jobs,
                observed_at=observed_at,
            ),
            self._current_service(
                service_id="storage",
                name="Document storage",
                status="operational" if storage_ready else "unavailable",
                observed_at=observed_at,
                activity=(
                    "Private storage check passed"
                    if storage_ready
                    else "Private storage check failed"
                ),
                evidence="Current storage readiness check; historical uptime is not recorded.",
                affected="Document access" if not storage_ready else None,
            ),
            self._export_service(export_runs, observed_at),
        ]

    def _provider_service(
        self,
        *,
        service_id: str,
        name: str,
        configured: str,
        runtime_name: str,
        jobs: list[ProcessingJob],
        observed_at: datetime,
    ) -> dict[str, object]:
        provider = configured.strip().casefold()
        is_mock = provider == "mock"
        relevant_failures = [
            job
            for job in jobs
            if job.status in FAILED_JOB_STATES
            and job.error_message
            and (
                runtime_name in job.error_message.casefold()
                or provider in job.error_message.casefold()
            )
        ]
        successful = [job for job in jobs if job.status == ProcessingJobStatus.SUCCEEDED]
        latest_failure = max((job.updated_at for job in relevant_failures), default=None)
        latest_success = max((job.updated_at for job in successful), default=None)
        latest = max((value for value in (latest_failure, latest_success) if value), default=None)
        if is_mock:
            status = "operational"
            evidence = "The local deterministic provider is available in this process."
        elif latest_failure is not None and (
            latest_success is None or latest_failure > latest_success
        ):
            status = "degraded"
            evidence = "The latest observed provider-specific processing attempt failed."
        elif latest_success is not None:
            status = "operational"
            evidence = "At least one invoice completed the provider-backed processing pipeline."
        else:
            status = "unknown"
            evidence = "Configuration is loaded, but no completed workspace run verifies this provider yet."
        return {
            "id": service_id,
            "name": name,
            "provider": configured,
            "status": status,
            "uptime": None,
            "uptime_label": "Not enough history",
            "observed_at": latest.isoformat()
            if latest
            else (observed_at.isoformat() if is_mock else None),
            "activity": (
                f"{len(successful)} completed pipeline runs"
                if successful
                else "No observed pipeline run"
            ),
            "evidence": evidence,
            "affected_capability": "Invoice processing" if status == "degraded" else None,
            "unaffected_capability": "Previously processed invoices remain available",
        }

    def _export_service(
        self, export_runs: list[ExportRunRecord], observed_at: datetime
    ) -> dict[str, object]:
        configured = self.settings.accounting_provider.strip().casefold()
        available = configured in {"csv_download", "mock"}
        latest = max(export_runs, key=lambda run: run.updated_at, default=None)
        if not available:
            status = "unavailable"
            evidence = "The configured accounting destination is not supported by this build."
        elif latest and latest.status == ExportRunStatus.FAILED:
            status = "degraded"
            evidence = "The latest export run failed; approved invoices remain unchanged."
        else:
            status = "operational"
            evidence = (
                "The latest export file was generated successfully."
                if latest
                else "The configured local export capability is available; no run has been observed yet."
            )
        return {
            "id": "accounting_export",
            "name": "Accounting export",
            "provider": configured,
            "status": status,
            "uptime": None,
            "uptime_label": "Not enough history",
            "observed_at": (latest.updated_at if latest else observed_at).isoformat(),
            "activity": (
                f"{len(export_runs)} recorded export runs"
                if export_runs
                else "No recorded export run"
            ),
            "evidence": evidence,
            "affected_capability": "Creating new accounting exports"
            if status != "operational"
            else None,
            "unaffected_capability": "Invoice review and stored records remain available",
        }

    @staticmethod
    def _current_service(
        *,
        service_id: str,
        name: str,
        status: str,
        observed_at: datetime,
        activity: str,
        evidence: str,
        affected: str | None,
    ) -> dict[str, object]:
        return {
            "id": service_id,
            "name": name,
            "provider": None,
            "status": status,
            "uptime": None,
            "uptime_label": "Not enough history",
            "observed_at": observed_at.isoformat(),
            "activity": activity,
            "evidence": evidence,
            "affected_capability": affected,
            "unaffected_capability": None,
        }

    @staticmethod
    def _overall(services: list[dict[str, object]]) -> dict[str, str]:
        states = {str(service["status"]) for service in services}
        if "unavailable" in states:
            return {
                "status": "unavailable",
                "title": "A core capability is unavailable",
                "detail": "Review the affected service before starting new work.",
            }
        if "degraded" in states:
            return {
                "status": "degraded",
                "title": "Operational with attention needed",
                "detail": "Most invoice capabilities remain available; one service has a recent failure.",
            }
        if "unknown" in states:
            return {
                "status": "unknown",
                "title": "Operational status is partially unverified",
                "detail": "Core local checks passed, but one or more providers need an observed run.",
            }
        return {
            "status": "operational",
            "title": "All observed services are operational",
            "detail": "Current readiness checks passed and no recent service failure is unresolved.",
        }

    def _alerts(
        self,
        services: list[dict[str, object]],
        jobs: list[ProcessingJob],
        documents: dict[object, DocumentRecord],
    ) -> list[dict[str, object]]:
        alerts = [
            {
                "id": f"service:{service['id']}",
                "kind": "service",
                "target_id": service["id"],
                "severity": "critical" if service["status"] == "unavailable" else "warning",
                "title": f"{service['name']} is {service['status']}",
                "detail": service["evidence"],
            }
            for service in services
            if service["status"] in {"degraded", "unavailable"}
        ]
        for job in sorted(
            (item for item in jobs if item.status in FAILED_JOB_STATES),
            key=lambda item: item.updated_at,
            reverse=True,
        )[:5]:
            document = documents[job.document_id]
            alerts.append(
                {
                    "id": f"job:{job.id}",
                    "kind": "job",
                    "target_id": str(job.id),
                    "severity": "critical"
                    if job.status == ProcessingJobStatus.DEAD_LETTER
                    else "warning",
                    "title": "Invoice processing needs attention",
                    "detail": f"{document.original_filename}: {self._safe_error(job.error_message)}",
                }
            )
        return alerts

    def _recent_jobs(
        self,
        jobs: list[ProcessingJob],
        documents: dict[object, DocumentRecord],
    ) -> list[dict[str, object]]:
        result = []
        for job in sorted(jobs, key=lambda item: item.updated_at, reverse=True)[:20]:
            document = documents[job.document_id]
            result.append(
                {
                    "id": str(job.id),
                    "document_id": str(document.id),
                    "invoice": self._invoice_label(document),
                    "filename": document.original_filename,
                    "stage": self._job_stage(job),
                    "status": job.status.value,
                    "started_at": (job.started_at or job.created_at).isoformat(),
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "duration_ms": self._duration_ms(job),
                    "attempt_count": job.attempt_count,
                    "retryable": job.status in FAILED_JOB_STATES
                    and document.status == DocumentStatus.FAILED,
                    "failure_summary": self._safe_error(job.error_message)
                    if job.status in FAILED_JOB_STATES
                    else None,
                }
            )
        return result

    def _flow(
        self,
        *,
        documents: list[DocumentRecord],
        events: list[AuditEvent],
        export_runs: list[ExportRunRecord],
        observed_at: datetime,
    ) -> dict[str, object]:
        cohort_date = observed_at.astimezone(UTC).date()
        cohort = {
            document.id
            for document in documents
            if document.created_at.astimezone(UTC).date() == cohort_date
        }
        event_documents: dict[str, set[object]] = {}
        for event in events:
            if event.document_id in cohort:
                event_documents.setdefault(event.event_type, set()).add(event.document_id)
        succeeded_jobs = {
            job.document_id
            for job in self.jobs.list_all()
            if job.document_id in cohort and job.status == ProcessingJobStatus.SUCCEEDED
        }
        attempted_exports = {
            document_id
            for run in export_runs
            if run.created_at.astimezone(UTC).date() == cohort_date
            for document_id in run.document_ids
            if document_id in cohort
        }
        counts = [
            ("upload", "Upload received", len(cohort)),
            ("read", "PDF read", len(succeeded_jobs)),
            ("extract", "Data extracted", len(event_documents.get("processing_finished", set()))),
            ("checks", "Checks completed", len(event_documents.get("review_required", set()))),
            ("export_attempt", "Export attempted", len(attempted_exports)),
            (
                "export_success",
                "Export succeeded",
                len(event_documents.get("document_exported", set())),
            ),
        ]
        previous: int | None = None
        stages = []
        for stage_id, label, count in counts:
            conversion = (
                100.0
                if previous is None and count
                else (round((count / previous) * 100, 1) if previous else None)
            )
            stages.append(
                {
                    "id": stage_id,
                    "label": label,
                    "count": count,
                    "previous_count": previous,
                    "conversion_percent": conversion,
                }
            )
            previous = count
        return {
            "window_label": f"Invoices uploaded on {cohort_date.isoformat()} UTC",
            "denominator": "Unique invoices from the upload cohort; conversion uses the previous stage.",
            "stages": stages,
        }

    def _integrations(self, services: list[dict[str, object]]) -> list[dict[str, object]]:
        by_id = {str(service["id"]): service for service in services}
        return [
            self._integration_row(by_id["reader"], "Document reader"),
            self._integration_row(by_id["extractor"], "Data extractor"),
            self._integration_row(by_id["storage"], "File storage"),
            self._integration_row(by_id["accounting_export"], "Accounting export"),
        ]

    @staticmethod
    def _integration_row(service: dict[str, object], name: str) -> dict[str, object]:
        return {
            "id": service["id"],
            "name": name,
            "provider": service["provider"],
            "status": service["status"],
            "observed_at": service["observed_at"],
            "evidence": service["evidence"],
        }

    @staticmethod
    def _audit(
        events: Iterable[AuditEvent], documents: dict[object, DocumentRecord]
    ) -> list[dict[str, object]]:
        return [
            {
                "id": str(event.id),
                "timestamp": event.created_at.isoformat(),
                "actor": event.actor,
                "action": event.event_type.replace("_", " ").title(),
                "target": documents[event.document_id].original_filename,
                "result": event.new_status.value if event.new_status else "recorded",
            }
            for event in sorted(events, key=lambda item: item.created_at, reverse=True)[:100]
        ]

    def _invoice_label(self, document: DocumentRecord) -> str:
        try:
            value = self.extractions.get_for_document(document.id).extraction_result.extraction.data
            return value.invoice_number or document.original_filename
        except NotFoundError:
            return document.original_filename

    @staticmethod
    def _job_stage(job: ProcessingJob) -> str:
        return {
            ProcessingJobStatus.QUEUED: "Waiting to read",
            ProcessingJobStatus.RETRYING: "Waiting to retry",
            ProcessingJobStatus.RUNNING: "Reading invoice",
            ProcessingJobStatus.SUCCEEDED: "Invoice checked",
            ProcessingJobStatus.FAILED: "Processing failed",
            ProcessingJobStatus.DEAD_LETTER: "Retry limit reached",
            ProcessingJobStatus.CANCELLED: "Processing cancelled",
        }[job.status]

    @staticmethod
    def _duration_ms(job: ProcessingJob) -> int | None:
        if job.started_at is None:
            return None
        end = job.finished_at or (
            datetime.now(UTC) if job.status == ProcessingJobStatus.RUNNING else None
        )
        if end is None:
            return None
        return max(0, round((end - job.started_at).total_seconds() * 1000))

    @staticmethod
    def _safe_error(error: str | None) -> str:
        if not error:
            return "Processing did not complete."
        normalized = error.casefold()
        if "mistral_ocr" in normalized or "parser" in normalized:
            return "The document reader did not complete the request."
        if "llm_json" in normalized or "extractor" in normalized:
            return "The data extractor did not complete the request."
        if "dead" in normalized:
            return "The retry limit was reached."
        return "Invoice processing did not complete."
