from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from app.core.security import SecurityContext, require_any_role
from app.extraction.schemas import InvoiceData, InvoiceLineItem
from app.review.models import (
    CorrectionEvent,
    CorrectionReasonSource,
    CorrectionSource,
    CorrectionValue,
    FieldCorrection,
)
from app.review.repositories import CorrectionEventRepository


INVOICE_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
)
LINE_ITEM_FIELDS = ("description", "quantity", "unit_price", "amount")


class CorrectionFeedbackService:
    def __init__(self, events: CorrectionEventRepository) -> None:
        self.events = events

    def capture(
        self,
        *,
        workspace_id: str,
        document_id: UUID,
        before: InvoiceData,
        after: InvoiceData,
        actor: str,
        reason: str | None,
        source: CorrectionSource,
        requested_reason: str | None = None,
    ) -> CorrectionEvent | None:
        existing = self.events.list_for_document(workspace_id, document_id)
        original_ai = existing[0].original_ai_data if existing else before
        changes = correction_diff(original_ai, before, after)
        if not changes:
            return None
        normalized_reason, reason_source = _correction_reason(reason, requested_reason)
        return self.events.add(
            CorrectionEvent(
                workspace_id=workspace_id,
                document_id=document_id,
                actor=actor,
                reason=normalized_reason,
                source=source,
                reason_source=reason_source,
                original_ai_data=original_ai,
                before_data=before,
                after_data=after,
                changes=changes,
            )
        )

    def list_for_document(
        self,
        document_id: UUID,
        context: SecurityContext,
    ) -> list[CorrectionEvent]:
        require_any_role(context, {"admin", "reviewer"})
        return self.events.list_for_document(context.workspace_id, document_id)

    def summary(self, workspace_id: str, document_id: UUID) -> dict[str, object] | None:
        events = self.events.list_for_document(workspace_id, document_id)
        if not events:
            return None
        latest = events[-1]
        return {
            "event_count": len(events),
            "latest_change_count": len(latest.changes),
            "latest_changed_fields": [change.field_path for change in latest.changes],
            "latest_actor": latest.actor,
            "latest_reason": latest.reason,
            "latest_at": latest.created_at.isoformat(),
        }


def correction_diff(
    original_ai: InvoiceData,
    before: InvoiceData,
    after: InvoiceData,
) -> tuple[FieldCorrection, ...]:
    original_values = flatten_invoice_data(original_ai)
    before_values = flatten_invoice_data(before)
    after_values = flatten_invoice_data(after)
    paths = sorted(set(before_values) | set(after_values))
    return tuple(
        FieldCorrection(
            field_path=path,
            original_ai_value=original_values.get(path),
            before_value=before_values.get(path),
            after_value=after_values.get(path),
        )
        for path in paths
        if before_values.get(path) != after_values.get(path)
    )


def flatten_invoice_data(data: InvoiceData) -> dict[str, CorrectionValue]:
    values = {field_name: _value(getattr(data, field_name)) for field_name in INVOICE_FIELDS}
    for index, item in enumerate(data.line_items):
        for field_name in LINE_ITEM_FIELDS:
            values[f"line_items[{index}].{field_name}"] = _value(getattr(item, field_name))
    return values


def invoice_data_to_dict(data: InvoiceData) -> dict[str, object]:
    return {
        **{field_name: _value(getattr(data, field_name)) for field_name in INVOICE_FIELDS},
        "line_items": [
            {field_name: _value(getattr(item, field_name)) for field_name in LINE_ITEM_FIELDS}
            for item in data.line_items
        ],
    }


def invoice_data_from_dict(value: dict[str, object]) -> InvoiceData:
    return InvoiceData(
        vendor_name=_optional_string(value.get("vendor_name")),
        invoice_number=_optional_string(value.get("invoice_number")),
        invoice_date=_optional_date(value.get("invoice_date")),
        due_date=_optional_date(value.get("due_date")),
        subtotal=_optional_decimal(value.get("subtotal")),
        tax=_optional_decimal(value.get("tax")),
        total=_optional_decimal(value.get("total")),
        currency=_optional_string(value.get("currency")),
        line_items=tuple(_line_item(item) for item in _dict_items(value.get("line_items"))),
    )


def correction_event_to_dict(event: CorrectionEvent) -> dict[str, object]:
    return {
        "schema_version": event.schema_version,
        "id": str(event.id),
        "workspace_id": event.workspace_id,
        "document_id": str(event.document_id),
        "actor": event.actor,
        "reason": event.reason,
        "source": event.source.value,
        "reason_source": event.reason_source.value,
        "original_ai_data": invoice_data_to_dict(event.original_ai_data),
        "before_data": invoice_data_to_dict(event.before_data),
        "after_data": invoice_data_to_dict(event.after_data),
        "changes": [
            {
                "field_path": change.field_path,
                "original_ai_value": change.original_ai_value,
                "before_value": change.before_value,
                "after_value": change.after_value,
            }
            for change in event.changes
        ],
        "created_at": event.created_at.isoformat(),
    }


def _correction_reason(
    reason: str | None,
    requested_reason: str | None,
) -> tuple[str, CorrectionReasonSource]:
    if reason and reason.strip():
        return reason.strip(), CorrectionReasonSource.USER
    if requested_reason and requested_reason.strip():
        return requested_reason.strip(), CorrectionReasonSource.REVIEWER_REQUEST
    return "Corrected while checking the invoice against the PDF.", CorrectionReasonSource.SYSTEM_DEFAULT


def _value(value: object) -> CorrectionValue:
    if isinstance(value, (date, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported correction value: {type(value).__name__}")


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None


def _optional_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _dict_items(value: object) -> Iterable[dict[str, object]]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, dict))


def _line_item(value: dict[str, object]) -> InvoiceLineItem:
    return InvoiceLineItem(
        description=_optional_string(value.get("description")),
        quantity=_optional_decimal(value.get("quantity")),
        unit_price=_optional_decimal(value.get("unit_price")),
        amount=_optional_decimal(value.get("amount")),
    )
