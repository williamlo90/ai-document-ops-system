from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable
from uuid import UUID

from app.backoffice.models import WorkflowEvent
from app.backoffice.repositories import WorkflowEventRepository
from app.core.security import SecurityContext, require_any_role
from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import (
    AuditRepository,
    DocumentRepository,
    ExtractionRepository,
    NotFoundError,
    StoredExtraction,
)
from app.documents.status import DocumentStatus


DECISION_EVENTS = {
    "document_approved": ("Invoice approved", "success"),
    "document_rejected": ("Invoice rejected", "danger"),
    "document_exported": ("Invoice exported", "info"),
}


@dataclass
class OverviewDashboardService:
    documents: DocumentRepository
    audits: AuditRepository
    extractions: ExtractionRepository
    workflow_events: WorkflowEventRepository

    def dashboard(
        self,
        context: SecurityContext,
        *,
        queue_rows: list[dict[str, object]],
        export_workspace: dict[str, object] | None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        require_any_role(context, {"admin", "reviewer"})
        observed_at = now or datetime.now(UTC)
        documents = self.documents.list_by_workspace(context.workspace_id)
        document_map = {document.id: document for document in documents}
        stored = {document.id: self._stored(document.id) for document in documents}
        audit_events = [
            event
            for document in documents
            for event in self.audits.list_for_document(document.id)
        ]
        correction_events = [
            event
            for document in documents
            for event in self.workflow_events.list_for_document(
                context.workspace_id, document.id
            )
            if event.event_type == "correction_requested"
        ]
        issue_rows = self._issue_rows(documents, stored)
        due_today = observed_at.astimezone(UTC).date().isoformat()
        due_today_count = sum(row.get("due_date") == due_today for row in queue_rows)
        waiting_review = sum(
            document.status == DocumentStatus.NEEDS_REVIEW
            and not self._has_errors(stored[document.id])
            for document in documents
        )
        needs_correction = sum(
            document.status == DocumentStatus.FAILED
            or (
                document.status == DocumentStatus.NEEDS_REVIEW
                and self._has_errors(stored[document.id])
            )
            for document in documents
        )
        approved = sum(
            document.status == DocumentStatus.APPROVED for document in documents
        )
        export_summary = export_workspace.get("summary", {}) if export_workspace else {}
        ready_export = self._summary_count(export_summary, "ready")
        blocking_documents = {
            str(issue["document_id"])
            for issue in issue_rows
            if issue["severity"] == "error"
        }
        failed_count = sum(
            document.status == DocumentStatus.FAILED for document in documents
        )
        findings = self._findings(issue_rows)
        return {
            "observed_at": observed_at.isoformat(),
            "actor": {
                "name": context.actor,
                "role": "Administrator" if context.is_admin else "Reviewer",
            },
            "briefing": self._briefing(
                attention_count=len(queue_rows) + failed_count,
                blocker_count=len(blocking_documents),
                due_today_count=due_today_count,
            ),
            "kpis": self._kpis(
                waiting_review=waiting_review,
                needs_correction=needs_correction,
                due_today=due_today_count,
                approved=approved,
                ready_export=ready_export,
                export_access=context.is_admin,
            ),
            "findings": findings,
            "alerts": self._alerts(
                blocker_count=len(blocking_documents),
                due_today_count=due_today_count,
                failed_count=failed_count,
                export_blocked=self._summary_count(export_summary, "blocked"),
                export_access=context.is_admin,
            ),
            "queue": {
                "total": len(queue_rows),
                "items": self._queue(queue_rows),
            },
            "throughput": self._throughput(audit_events, observed_at),
            "exception_breakdown": self._exception_breakdown(issue_rows),
            "pipeline": self._pipeline(documents),
            "recent_decisions": self._recent_decisions(
                document_map=document_map,
                stored=stored,
                audit_events=audit_events,
                correction_events=correction_events,
            ),
            "capabilities": {
                "export_access": context.is_admin,
                "due_policy": False,
                "sla_policy": False,
                "historical_issue_snapshots": False,
            },
        }

    @staticmethod
    def _briefing(
        *, attention_count: int, blocker_count: int, due_today_count: int
    ) -> dict[str, object]:
        if attention_count == 0:
            return {
                "attention_count": 0,
                "title": "No invoices need attention",
                "detail": "The review queue and failed-processing list are clear.",
                "action_label": "View all invoices",
                "action_href": "/invoices",
            }
        details = [f"{blocker_count} blocked by validation"]
        if due_today_count:
            details.append(f"{due_today_count} with an invoice due date today")
        return {
            "attention_count": attention_count,
            "title": f"{attention_count} invoices need attention",
            "detail": "; ".join(details) + ".",
            "action_label": "Review priority invoices",
            "action_href": "/review-queue?sort=risk&direction=desc",
        }

    @staticmethod
    def _kpis(
        *,
        waiting_review: int,
        needs_correction: int,
        due_today: int,
        approved: int,
        ready_export: int,
        export_access: bool,
    ) -> list[dict[str, object]]:
        fourth = (
            {
                "id": "ready_export",
                "label": "Ready to export",
                "count": ready_export,
                "note": "Approved and eligible",
                "tone": "teal",
                "href": "/exports?status=ready",
            }
            if export_access
            else {
                "id": "approved",
                "label": "Approved",
                "count": approved,
                "note": "Reviewer decisions recorded",
                "tone": "teal",
                "href": "/invoices?status=approved",
            }
        )
        return [
            {
                "id": "waiting_review",
                "label": "Waiting for review",
                "count": waiting_review,
                "note": "Ready for a decision",
                "tone": "blue",
                "href": "/invoices?status=needs_review",
            },
            {
                "id": "needs_correction",
                "label": "Needs correction",
                "count": needs_correction,
                "note": "Validation or processing issue",
                "tone": "red",
                "href": "/invoices?status=needs_correction",
            },
            {
                "id": "due_today",
                "label": "Invoice due today",
                "count": due_today,
                "note": "Based on the invoice due date",
                "tone": "orange",
                "href": "/review-queue?sort=due_date&direction=asc",
            },
            fourth,
        ]

    @staticmethod
    def _alerts(
        *,
        blocker_count: int,
        due_today_count: int,
        failed_count: int,
        export_blocked: int,
        export_access: bool,
    ) -> list[dict[str, object]]:
        alerts: list[dict[str, object]] = []
        if blocker_count:
            alerts.append(
                {
                    "id": "validation_blockers",
                    "title": f"{blocker_count} invoices cannot be approved",
                    "detail": "Resolve their blocking validation findings first.",
                    "severity": "critical",
                    "href": "/exceptions?scope=blocking",
                }
            )
        if due_today_count:
            alerts.append(
                {
                    "id": "due_today",
                    "title": f"{due_today_count} invoice due dates are today",
                    "detail": "Review these invoices before their recorded due date passes.",
                    "severity": "warning",
                    "href": "/review-queue?sort=due_date&direction=asc",
                }
            )
        if failed_count:
            alerts.append(
                {
                    "id": "processing_failed",
                    "title": f"{failed_count} invoices failed processing",
                    "detail": "Open the invoice record to retry or inspect the failure.",
                    "severity": "warning",
                    "href": "/invoices?status=needs_correction",
                }
            )
        if export_access and export_blocked:
            alerts.append(
                {
                    "id": "export_blocked",
                    "title": f"{export_blocked} invoices are blocked from export",
                    "detail": "Approval or validation requirements are still incomplete.",
                    "severity": "info",
                    "href": "/exports?status=blocked",
                }
            )
        return alerts[:4]

    @staticmethod
    def _queue(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        risk_order = {"high": 3, "medium": 2, "low": 1}
        ordered = sorted(
            rows,
            key=lambda row: (
                risk_order.get(str(row.get("risk")), 0),
                str(row.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return [
            {
                "document_id": str(row["id"]),
                "invoice_number": row.get("invoice_number") or row.get("original_filename"),
                "vendor_name": row.get("vendor_name") or "Vendor not detected",
                "total": row.get("total"),
                "currency": row.get("currency"),
                "finding": row.get("finding") or "No blocking finding",
                "risk": row.get("risk"),
                "confidence": row.get("confidence"),
                "due_date": row.get("due_date"),
                "owner": row.get("owner") or "Review team",
                "recommended_action": row.get("recommended_action"),
                "href": f"/review/{row['id']}",
            }
            for row in ordered[:6]
        ]

    def _findings(self, issues: list[dict[str, object]]) -> list[dict[str, object]]:
        definitions = (
            ("missing_fields", "Missing required fields", "vendor_invoice", "blue"),
            ("duplicates", "Possible duplicates", "duplicate", "purple"),
            ("amounts", "Tax or amount issues", "tax_amount", "orange"),
        )
        result = []
        for finding_id, label, category, tone in definitions:
            document_count = len(
                {
                    str(issue["document_id"])
                    for issue in issues
                    if issue["finding_group"] == finding_id
                }
            )
            result.append(
                {
                    "id": finding_id,
                    "label": label,
                    "count": document_count,
                    "tone": tone,
                    "href": f"/exceptions?category={category}",
                }
            )
        return result

    def _throughput(
        self, audit_events: Iterable[AuditEvent], observed_at: datetime
    ) -> dict[str, object]:
        end = observed_at.astimezone(UTC).date()
        dates = [end - timedelta(days=offset) for offset in range(6, -1, -1)]
        processed: dict[date, set[object]] = defaultdict(set)
        sent_for_review: dict[date, set[object]] = defaultdict(set)
        for event in audit_events:
            day = event.created_at.astimezone(UTC).date()
            if event.event_type == "processing_finished":
                processed[day].add(event.document_id)
            elif event.event_type == "review_required":
                sent_for_review[day].add(event.document_id)
        return {
            "window_label": "Last 7 days (UTC)",
            "series": [
                {"id": "processed", "label": "Processed"},
                {"id": "sent_for_review", "label": "Sent for review"},
            ],
            "points": [
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%b %d"),
                    "processed": len(processed[day]),
                    "sent_for_review": len(sent_for_review[day]),
                }
                for day in dates
            ],
            "method": "Unique invoices recorded by processing and review audit events.",
        }

    @staticmethod
    def _exception_breakdown(
        issues: list[dict[str, object]],
    ) -> dict[str, object]:
        definitions = (
            ("vendor_invoice", "Vendor / invoice", "#2563eb"),
            ("tax_amount", "Tax / amount", "#f59e0b"),
            ("duplicate", "Duplicate", "#7c3aed"),
            ("dates_details", "Dates / details", "#0f9fa8"),
            ("other", "Other", "#64748b"),
        )
        counts: dict[str, int] = defaultdict(int)
        for issue in issues:
            counts[str(issue["category"])] += 1
        total = len(issues)
        return {
            "total": total,
            "categories": [
                {
                    "id": category,
                    "label": label,
                    "count": counts[category],
                    "percentage": round((counts[category] / total) * 100) if total else 0,
                    "color": color,
                    "href": f"/exceptions?category={category}",
                }
                for category, label, color in definitions
                if counts[category]
            ],
        }

    @staticmethod
    def _pipeline(documents: list[DocumentRecord]) -> dict[str, object]:
        stage_definitions = (
            (
                "uploaded",
                "Uploaded",
                {DocumentStatus.UPLOADED, DocumentStatus.QUEUED},
                "/invoices?status=open",
            ),
            (
                "reading",
                "Reading",
                {DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED},
                "/invoices?status=open",
            ),
            (
                "waiting_review",
                "Waiting for review",
                {DocumentStatus.NEEDS_REVIEW},
                "/review-queue",
            ),
            (
                "approved",
                "Approved",
                {DocumentStatus.APPROVED},
                "/invoices?status=approved",
            ),
            (
                "exported",
                "Exported",
                {DocumentStatus.EXPORTED},
                "/invoices?status=exported",
            ),
        )
        included = set().union(*(statuses for _, _, statuses, _ in stage_definitions))
        return {
            "items": [
                {
                    "id": stage_id,
                    "label": label,
                    "count": sum(document.status in statuses for document in documents),
                    "href": href,
                }
                for stage_id, label, statuses, href in stage_definitions
            ],
            "excluded_count": sum(document.status not in included for document in documents),
            "note": "Rejected, failed, and cancelled invoices are excluded from the main pipeline.",
        }

    def _recent_decisions(
        self,
        *,
        document_map: dict[object, DocumentRecord],
        stored: dict[object, StoredExtraction | None],
        audit_events: list[AuditEvent],
        correction_events: list[WorkflowEvent],
    ) -> list[dict[str, object]]:
        decisions: list[tuple[datetime, dict[str, object]]] = []
        for event in audit_events:
            definition = DECISION_EVENTS.get(event.event_type)
            if definition is None or event.document_id not in document_map:
                continue
            title, tone = definition
            decisions.append(
                (
                    event.created_at,
                    self._decision_item(
                        event_id=str(event.id),
                        document=document_map[event.document_id],
                        stored=stored[event.document_id],
                        title=title,
                        actor=event.actor,
                        occurred_at=event.created_at,
                        tone=tone,
                    ),
                )
            )
        for event in correction_events:
            if event.document_id is None or event.document_id not in document_map:
                continue
            decisions.append(
                (
                    event.created_at,
                    self._decision_item(
                        event_id=str(event.id),
                        document=document_map[event.document_id],
                        stored=stored[event.document_id],
                        title="Correction requested",
                        actor=event.actor,
                        occurred_at=event.created_at,
                        tone="warning",
                    ),
                )
            )
        return [item for _, item in sorted(decisions, key=lambda item: item[0], reverse=True)[:6]]

    @staticmethod
    def _decision_item(
        *,
        event_id: str,
        document: DocumentRecord,
        stored: StoredExtraction | None,
        title: str,
        actor: str,
        occurred_at: datetime,
        tone: str,
    ) -> dict[str, object]:
        data = stored.extraction_result.extraction.data if stored else None
        return {
            "id": event_id,
            "document_id": str(document.id),
            "title": title,
            "invoice": data.invoice_number if data and data.invoice_number else document.original_filename,
            "vendor": data.vendor_name if data and data.vendor_name else "Vendor not detected",
            "actor": actor,
            "occurred_at": occurred_at.isoformat(),
            "tone": tone,
            "href": f"/review/{document.id}",
        }

    def _issue_rows(
        self,
        documents: list[DocumentRecord],
        stored: dict[object, StoredExtraction | None],
    ) -> list[dict[str, object]]:
        rows = []
        for document in documents:
            extraction = stored[document.id]
            if document.status != DocumentStatus.NEEDS_REVIEW or extraction is None:
                continue
            for issue in extraction.validation_report.issues:
                category = self._issue_category(issue.code, issue.field_name)
                rows.append(
                    {
                        "document_id": str(document.id),
                        "code": issue.code,
                        "severity": issue.severity.value,
                        "category": category,
                        "finding_group": self._finding_group(issue.code, category),
                    }
                )
        return rows

    @staticmethod
    def _issue_category(code: str, field_name: str) -> str:
        normalized = f"{code} {field_name}".casefold()
        if "duplicate" in normalized:
            return "duplicate"
        if any(value in normalized for value in ("vendor", "invoice_number")):
            return "vendor_invoice"
        if any(value in normalized for value in ("tax", "total", "amount", "currency")):
            return "tax_amount"
        if any(value in normalized for value in ("date", "line_item")):
            return "dates_details"
        return "other"

    @staticmethod
    def _finding_group(code: str, category: str) -> str:
        if code == "missing_critical_field":
            return "missing_fields"
        if category == "duplicate":
            return "duplicates"
        if category == "tax_amount":
            return "amounts"
        return "other"

    def _stored(self, document_id: UUID) -> StoredExtraction | None:
        try:
            return self.extractions.get_for_document(document_id)
        except NotFoundError:
            return None

    @staticmethod
    def _has_errors(stored: StoredExtraction | None) -> bool:
        return bool(stored and stored.validation_report.has_errors)

    @staticmethod
    def _summary_count(summary: object, key: str) -> int:
        if not isinstance(summary, dict):
            return 0
        value = summary.get(key)
        if not isinstance(value, dict):
            return 0
        return int(value.get("count") or 0)
