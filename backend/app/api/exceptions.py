from __future__ import annotations

import csv
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import AppContainer, get_container, require_review_context
from app.api.document_workflow import current_work_item, extraction_or_none
from app.backoffice.models import WorkType
from app.core.security import SecurityContext
from app.documents.status import DocumentStatus


router = APIRouter(prefix="/exceptions", tags=["exceptions"])


class ExceptionAssignmentPayload(BaseModel):
    assignee: str | None = Field(default=None, max_length=120)

    @field_validator("assignee")
    @classmethod
    def normalize_assignee(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None


@router.get("")
def list_exceptions(
    search: str = Query(default="", max_length=120),
    scope: str = Query(default="all", pattern="^(all|blocking|warnings)$"),
    category: str = Query(
        default="", pattern="^(|vendor_invoice|tax_amount|duplicate|dates_details|other)$"
    ),
    risk: str = Query(default="", pattern="^(|high|medium)$"),
    owner: str = Query(default="", max_length=120),
    sort: str = Query(default="risk", pattern="^(risk|age|updated|issue)$"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    rows = _filter_rows(
        _open_exception_rows(container, context),
        search=search,
        scope=scope,
        category=category,
        risk=risk,
        owner=owner,
    )
    _sort_rows(rows, sort, direction)
    total = len(rows)
    start = (page - 1) * page_size
    categories = Counter(str(row["category"]) for row in rows)
    top_issues = Counter((str(row["issue"]), str(row["category"])) for row in rows).most_common(3)
    return {
        "items": [_exception_summary(row) for row in rows[start : start + page_size]],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "summary": {
            "open_exceptions": total,
            "high_risk": sum(row["risk"] == "high" for row in rows),
            "warning_issues": sum(row["risk"] == "medium" for row in rows),
            "invoices_affected": len({row["document_id"] for row in rows}),
            "categories": dict(categories),
            "top_issues": [
                {"label": label, "category": issue_category, "count": count}
                for (label, issue_category), count in top_issues
            ],
        },
        "assignee_options": sorted(
            {
                context.actor,
                *(str(row["owner"]) for row in rows if row["owner"]),
            }
        ),
        "capabilities": {
            "resolved_history": False,
            "due_policy": False,
            "validated_resolution_only": True,
        },
    }


@router.get("/export")
def export_exceptions(
    search: str = Query(default="", max_length=120),
    scope: str = Query(default="all", pattern="^(all|blocking|warnings)$"),
    category: str = Query(
        default="", pattern="^(|vendor_invoice|tax_amount|duplicate|dates_details|other)$"
    ),
    risk: str = Query(default="", pattern="^(|high|medium)$"),
    owner: str = Query(default="", max_length=120),
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> Response:
    rows = _filter_rows(
        _open_exception_rows(container, context),
        search=search,
        scope=scope,
        category=category,
        risk=risk,
        owner=owner,
    )
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "exception_id",
            "invoice",
            "vendor",
            "issue",
            "risk",
            "owner",
            "detected_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["invoice_number"] or row["original_filename"],
                row["vendor_name"] or "",
                row["issue"],
                row["risk"],
                row["owner"] or "Unassigned",
                row["detected_at"],
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="open-exceptions.csv"'},
    )


@router.get("/{exception_id}")
def get_exception(
    exception_id: str,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    row = _required_exception(exception_id, container, context)
    return {"exception": row}


@router.patch("/{exception_id}/assignment")
def assign_exception(
    exception_id: str,
    payload: ExceptionAssignmentPayload,
    context: SecurityContext = Depends(require_review_context),
    container: AppContainer = Depends(get_container),
) -> dict[str, object]:
    row = _required_exception(exception_id, container, context)
    document_id = UUID(str(row["document_id"]))
    work_item = current_work_item(container, context, document_id)
    if work_item is None:
        work_item = container.backoffice_service.create_work_item(
            title=f"Resolve {row['issue']}",
            context=context,
            work_type=WorkType.EXCEPTION_HANDLING,
            linked_document_ids=(document_id,),
            business_context={"requested_outcome": str(row["required_action"])},
            idempotency_key=f"exception:{document_id}",
        )
    work_item = container.backoffice_service.update_work_item(
        work_item_id=work_item.id,
        context=context,
        assignee=payload.assignee or "",
    )
    updated = _required_exception(exception_id, container, context)
    return {
        "exception": updated,
        "assignment": {
            "work_item_id": str(work_item.id),
            "assignee": payload.assignee,
            "recorded_by": context.actor,
            "recorded_at": work_item.updated_at.isoformat(),
        },
    }


def _open_exception_rows(
    container: AppContainer, context: SecurityContext
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    now = datetime.now(UTC)
    for document in container.documents.list_by_workspace(context.workspace_id):
        if document.status != DocumentStatus.NEEDS_REVIEW:
            continue
        extraction = extraction_or_none(container, document.id)
        if extraction is None:
            continue
        data = extraction.extraction_result.extraction.data
        work_item = current_work_item(container, context, document.id)
        owner = work_item.business_context.get("assignee") if work_item else None
        for issue in extraction.validation_report.issues:
            issue_id = _exception_id(document.id, issue.code, issue.field_name, issue.message)
            blocks_approval = issue.severity.value == "error"
            issue_title = _issue_title(issue.code, issue.field_name)
            rows.append(
                {
                    "id": issue_id,
                    "document_id": str(document.id),
                    "work_item_id": str(work_item.id) if work_item else None,
                    "original_filename": document.original_filename,
                    "invoice_number": data.invoice_number,
                    "vendor_name": data.vendor_name,
                    "total": str(data.total) if data.total is not None else None,
                    "currency": data.currency,
                    "issue": issue_title,
                    "message": _plain_message(issue.message),
                    "code": issue.code,
                    "field_name": issue.field_name,
                    "field_value": _field_value(data, issue.field_name),
                    "category": _category(issue.code, issue.field_name),
                    "risk": "high" if blocks_approval else "medium",
                    "blocks_approval": blocks_approval,
                    "owner": owner,
                    "detected_at": document.updated_at.isoformat(),
                    "age_seconds": max(0, int((now - document.updated_at).total_seconds())),
                    "required_action": _required_action(issue.code, issue.field_name),
                    "related_checks": _related_checks(
                        data.vendor_name, issue_title, blocks_approval
                    ),
                }
            )
    return rows


def _filter_rows(
    rows: list[dict[str, object]],
    *,
    search: str,
    scope: str,
    category: str,
    risk: str,
    owner: str,
) -> list[dict[str, object]]:
    needle = search.strip().casefold()
    owner_filter = owner.strip().casefold()
    return [
        row
        for row in rows
        if (
            not needle
            or needle
            in " ".join(
                str(row.get(key) or "")
                for key in (
                    "issue",
                    "message",
                    "invoice_number",
                    "vendor_name",
                    "original_filename",
                )
            ).casefold()
        )
        and (scope != "blocking" or row["blocks_approval"])
        and (scope != "warnings" or not row["blocks_approval"])
        and (not category or row["category"] == category)
        and (not risk or row["risk"] == risk)
        and (not owner_filter or owner_filter in str(row["owner"] or "Unassigned").casefold())
    ]


def _sort_rows(rows: list[dict[str, object]], sort: str, direction: str) -> None:
    risk_order = {"medium": 1, "high": 2}

    def value(row: dict[str, object]):
        if sort == "risk":
            return (risk_order[str(row["risk"])], row["age_seconds"])
        if sort == "age":
            return row["age_seconds"]
        if sort == "issue":
            return str(row["issue"]).casefold()
        return row["detected_at"]

    rows.sort(key=value, reverse=direction == "desc")


def _required_exception(
    exception_id: str, container: AppContainer, context: SecurityContext
) -> dict[str, object]:
    match = next(
        (row for row in _open_exception_rows(container, context) if row["id"] == exception_id),
        None,
    )
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return match


def _exception_summary(row: dict[str, object]) -> dict[str, object]:
    return {
        key: row[key]
        for key in (
            "id",
            "document_id",
            "work_item_id",
            "original_filename",
            "invoice_number",
            "vendor_name",
            "total",
            "currency",
            "issue",
            "category",
            "risk",
            "blocks_approval",
            "owner",
            "detected_at",
            "age_seconds",
        )
    }


def _exception_id(document_id: UUID, code: str, field_name: str, message: str) -> str:
    payload = f"{document_id}|{code}|{field_name}|{message}".encode()
    return sha256(payload).hexdigest()[:20]


def _issue_title(code: str, field_name: str) -> str:
    field = _field_label(field_name)
    return {
        "missing_critical_field": f"Missing {field}",
        "invalid_total": "Invalid invoice total",
        "total_mismatch": "Invoice total does not match",
        "invalid_date_order": "Invoice dates are inconsistent",
        "unsupported_currency": "Unsupported currency",
        "line_item_amount_mismatch": "Line item amount does not match",
        "duplicate_invoice": "Possible duplicate invoice",
    }.get(code, field)


def _category(code: str, field_name: str) -> str:
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


def _required_action(code: str, field_name: str) -> str:
    field = _field_label(field_name)
    if code == "duplicate_invoice":
        return "Compare the matching invoice before making a reviewer decision."
    if code == "missing_critical_field":
        return f"Add or request a valid {field}, then save the invoice so validation can run again."
    return f"Check {field} against the PDF, correct it if needed, and rerun validation."


def _related_checks(
    vendor_name: str | None, issue_title: str, blocks_approval: bool
) -> list[dict[str, str]]:
    return [
        {"label": "Invoice extracted", "status": "passed"},
        {
            "label": "Vendor detected",
            "status": "passed" if vendor_name else "blocked",
        },
        {
            "label": issue_title,
            "status": "blocked" if blocks_approval else "warning",
        },
    ]


def _field_value(data, field_name: str) -> str | None:
    if field_name.startswith("line_items["):
        return None
    value = getattr(data, field_name, None)
    return str(value) if value not in (None, "") else None


def _field_label(field_name: str) -> str:
    if field_name.startswith("line_items["):
        return "line item amount"
    return field_name.replace("_", " ")


def _plain_message(message: str) -> str:
    normalized = message.replace("_", " ")
    return normalized[:1].upper() + normalized[1:].rstrip(".") + "."
