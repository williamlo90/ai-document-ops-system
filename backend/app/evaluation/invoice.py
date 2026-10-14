from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.evaluation.line_items import evaluate_line_items, validate_lines, required_fields


from app.evaluation.provenance import fields_have_labels, fields_match

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
    quality: dict[str, Any]


def evaluate_invoices(
    expected_records: list[dict[str, Any]],
    predicted_records: list[dict[str, Any]],
) -> EvaluationReport:
    _validate_expected_records(expected_records)
    validate_record_ids(predicted_records, "Predicted")
    predicted_by_id = {
        str(record["document_id"]): record
        for record in predicted_records
        if not record.get("error")
    }
    evaluations: list[FieldEvaluation] = []
    header_exact = 0
    for expected in expected_records:
        document_id = str(expected["document_id"])
        has_prediction = document_id in predicted_by_id
        predicted = predicted_by_id.get(document_id, {})
        document_matches = []
        for field_name in EVALUATED_FIELDS:
            item = _evaluate_field(document_id, field_name, expected, predicted, has_prediction)
            document_matches.append(item.matched)
            evaluations.append(item)
        header_exact += int(all(document_matches))
    matched = sum(1 for item in evaluations if item.matched)
    fields_total = len(evaluations)
    line_quality = evaluate_line_items(expected_records, predicted_by_id)
    header_failed_ids = {item.document_id for item in evaluations if not item.matched}
    fully_labeled = {
        r["document_id"]
        for r in expected_records
        if "line_items" in r
        and fields_have_labels(r, EVALUATED_FIELDS)
        and all(fields_have_labels(row, required_fields(row)) for row in r["line_items"])
    }
    full_total = len(fully_labeled)
    expected_by_id = {r["document_id"]: r for r in expected_records}
    full_matched = sum(
        item["exact"]
        and item["provenance_exact"]
        and item["document_id"] not in header_failed_ids
        and fields_match(
            expected_by_id[item["document_id"]],
            predicted_by_id.get(item["document_id"], {}),
            EVALUATED_FIELDS,
        )
        for item in line_quality.pop("document_results")
        if item["document_id"] in fully_labeled
    )
    return EvaluationReport(
        documents_total=len(expected_records),
        fields_total=fields_total,
        fields_matched=matched,
        field_accuracy=matched / fields_total if fields_total else 0,
        by_field=_accuracy_by_field(evaluations),
        failures=tuple(item for item in evaluations if not item.matched),
        quality={
            "header_field_accuracy": ratio(matched, fields_total),
            "header_exact_match_rate": ratio(header_exact, len(expected_records)),
            "full_invoice_exact_match_rate": ratio(full_matched, full_total),
            "full_invoice_documents_matched": full_matched,
            "full_invoice_documents_total": full_total,
            "full_invoice_label_coverage": ratio(full_total, len(expected_records)),
            "line_items": line_quality,
        },
    )


def _evaluate_field(
    document_id: str,
    field_name: str,
    expected: dict[str, Any],
    predicted: dict[str, Any],
    has_prediction: bool,
) -> FieldEvaluation:
    expected_value = _normalized(field_name, expected.get(field_name))
    try:
        predicted_value = _normalized(field_name, predicted.get(field_name))
        valid = field_name in predicted
    except ValueError:
        predicted_value = str(predicted.get(field_name))
        valid = False
    return FieldEvaluation(
        document_id,
        field_name,
        expected_value,
        predicted_value,
        has_prediction and valid and expected_value == predicted_value,
    )


def report_to_dict(report: EvaluationReport) -> dict[str, Any]:
    return {
        "report_version": "2.1",
        "contract_version": "2.0.0",
        "metric_scope": "header_lines_and_oracle_provenance",
        "legacy_metric_scope": "header_only",
        "evaluation_input": "supplied_records",
        **report.quality,
        "documents_total": report.documents_total,
        "fields_total": report.fields_total,
        "fields_matched": report.fields_matched,
        "field_accuracy": round(report.field_accuracy, 4) if report.fields_total else None,
        "by_field": {
            key: round(value, 4) if report.documents_total else None
            for key, value in report.by_field.items()
        },
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
    validate_record_ids(expected_records, "Expected")
    required = {"document_id", *EVALUATED_FIELDS}
    for index, record in enumerate(expected_records):
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(
                f"Expected invoice record at index {index} is missing fields: {', '.join(missing)}"
            )
        if "line_items" in record:
            validate_lines(record["line_items"], expected=True)


def validate_record_ids(records: list[dict[str, Any]], label: str) -> None:
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{label} record must be an object")
        identity = record.get("document_id")
        if not isinstance(identity, str) or not identity.strip() or identity != identity.strip():
            raise ValueError(f"{label} document_id must be a non-empty trimmed string")
        if identity in seen:
            raise ValueError(f"Duplicate {label.lower()} document_id: {identity}")
        seen.add(identity)


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _normalized(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    if field_name in MONEY_FIELDS:
        return _money(value)
    if field_name in {"invoice_date", "due_date"}:
        try:
            return date.fromisoformat(str(value).strip()).isoformat()
        except ValueError as exc:
            raise ValueError(f"Invalid ISO date: {value}") from exc
    return (
        " ".join(str(value).split()).casefold()
        if field_name in {"vendor_name", "currency"}
        else str(value).strip()
    )


def _money(value: Any) -> str:
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return str(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid money value: {value}") from exc
