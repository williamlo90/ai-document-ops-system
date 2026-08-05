from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


EVALUATED_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
)

MONEY_FIELDS = {"subtotal", "tax", "total"}


@dataclass(frozen=True)
class FieldEvaluation:
    document_id: str
    field_name: str
    expected: str | None
    predicted: str | None
    matched: bool


@dataclass(frozen=True)
class EvaluationReport:
    documents_total: int
    fields_total: int
    fields_matched: int
    field_accuracy: float
    by_field: dict[str, float]
    failures: tuple[FieldEvaluation, ...]


def evaluate_invoices(
    expected_records: list[dict[str, Any]],
    predicted_records: list[dict[str, Any]],
) -> EvaluationReport:
    _validate_expected_records(expected_records)
    predicted_by_id = {str(record["document_id"]): record for record in predicted_records}
    evaluations: list[FieldEvaluation] = []
    for expected in expected_records:
        document_id = str(expected["document_id"])
        has_prediction = document_id in predicted_by_id
        predicted = predicted_by_id.get(document_id, {})
        for field_name in EVALUATED_FIELDS:
            expected_value = _normalized(field_name, expected.get(field_name))
            predicted_value = _normalized(field_name, predicted.get(field_name))
            evaluations.append(
                FieldEvaluation(
                    document_id=document_id,
                    field_name=field_name,
                    expected=expected_value,
                    predicted=predicted_value,
                    matched=has_prediction and expected_value == predicted_value,
                )
            )
    matched = sum(1 for item in evaluations if item.matched)
    fields_total = len(evaluations)
    return EvaluationReport(
        documents_total=len(expected_records),
        fields_total=fields_total,
        fields_matched=matched,
        field_accuracy=matched / fields_total if fields_total else 0,
        by_field=_accuracy_by_field(evaluations),
        failures=tuple(item for item in evaluations if not item.matched),
    )


def report_to_dict(report: EvaluationReport) -> dict[str, Any]:
    return {
        "documents_total": report.documents_total,
        "fields_total": report.fields_total,
        "fields_matched": report.fields_matched,
        "field_accuracy": round(report.field_accuracy, 4),
        "by_field": {key: round(value, 4) for key, value in report.by_field.items()},
        "failures": [
            {
                "document_id": item.document_id,
                "field_name": item.field_name,
                "expected": item.expected,
                "predicted": item.predicted,
            }
            for item in report.failures
        ],
    }


def _accuracy_by_field(evaluations: list[FieldEvaluation]) -> dict[str, float]:
    result: dict[str, float] = {}
    for field_name in EVALUATED_FIELDS:
        field_items = [item for item in evaluations if item.field_name == field_name]
        result[field_name] = (
            sum(1 for item in field_items if item.matched) / len(field_items) if field_items else 0
        )
    return result


def _validate_expected_records(expected_records: list[dict[str, Any]]) -> None:
    required = {"document_id", *EVALUATED_FIELDS}
    for index, record in enumerate(expected_records):
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(
                f"Expected invoice record at index {index} is missing fields: {', '.join(missing)}"
            )


def _normalized(field_name: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    if field_name in MONEY_FIELDS:
        return _money(value)
    return (
        str(value).strip().casefold()
        if field_name in {"vendor_name", "currency"}
        else str(value).strip()
    )


def _money(value: Any) -> str:
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money value: {value}") from exc
