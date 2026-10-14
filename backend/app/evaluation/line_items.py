"""One-to-one, order-independent comparison; no model or business tolerance involved."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.evaluation.provenance import fields_match

LINE_FIELDS = ("description", "uom", "quantity", "unit_price", "amount")
OPTIONAL_FIELDS = ("tax", "discount", "purchase_order", "purchase_receipt", "item_reference")


def required_fields(line: dict) -> tuple[str, ...]:
    return LINE_FIELDS + tuple(f for f in OPTIONAL_FIELDS if f in line)


ALIGNMENT_VERSION = "reference_description_uom_multiset_v2"


def _value(field: str, value: Any) -> str | None:
    if value is None:
        return None
    if field in {"description", "uom", "purchase_order", "purchase_receipt", "item_reference"}:
        if not isinstance(value, str):
            raise ValueError("description must be text or null")
        return " ".join(value.split()).casefold()
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        # Quantity and unit price retain precision; printed line amount uses cents.
        if field == "amount":
            number = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return str(number.normalize())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid line {field}: {value}") from exc


def validate_lines(value: Any, *, expected: bool) -> None:
    if not isinstance(value, list):
        raise ValueError("line_items must be a list (use [] for explicitly no lines)")
    for line in value:
        if not isinstance(line, dict):
            raise ValueError("Each line item must be an object")
        if expected:
            missing = (set(LINE_FIELDS) - {"uom"}) - line.keys()
            if missing:
                raise ValueError(f"Expected line item missing fields: {', '.join(sorted(missing))}")
            for field in required_fields(line):
                _value(field, line.get(field))


def _normalized(line: dict[str, Any]) -> tuple[str | None, ...]:
    values = []
    for field in required_fields(line):
        try:
            values.append(_value(field, line.get(field)))
        except ValueError:
            # Invalid predictions remain wrong; do not abort a whole evaluation run.
            values.append(f"<invalid:{field}>")
    return tuple(values)


def _pairs(expected: list[dict], predicted: list[dict]) -> tuple[list[tuple[int, int]], int]:
    groups = defaultdict(lambda: ([], []))

    def identity(row):
        if row.get("line_reference"):
            return ("reference", str(row["line_reference"]))
        return ("identity", _normalized(row)[:2])

    for i, row in enumerate(expected):
        groups[identity(row)][0].append(i)
    for j, row in enumerate(predicted):
        groups[identity(row)][1].append(j)
    pairs, ambiguous = [], 0
    for key, (left, right) in groups.items():
        if not left or not right:
            continue
        # Repeated *identical* rows are a multiset. Non-identical rows sharing an
        # identity are ambiguous even when a numeric permutation would score well.
        same_expected = len({_normalized(expected[i]) for i in left}) == 1
        same_predicted = len({_normalized(predicted[j]) for j in right}) == 1
        if max(len(left), len(right)) > 1 and (
            key[0] == "reference" or not same_expected or not same_predicted
        ):
            ambiguous += 1
            continue
        pairs.extend(zip(left, right, strict=False))
    return pairs, ambiguous


def evaluate_line_items(
    expected_records: list[dict[str, Any]], predicted_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    labeled = expected_total = predicted_total = matched = exact_lines = missing = extra = 0
    by_field = dict.fromkeys(LINE_FIELDS, 0)
    failures: list[dict[str, Any]] = []
    documents = []
    invalid_documents = 0
    ambiguous_groups = 0
    total_fields = 0
    field_denominators = dict.fromkeys(LINE_FIELDS + OPTIONAL_FIELDS, 0)
    by_field = dict.fromkeys(LINE_FIELDS + OPTIONAL_FIELDS, 0)
    for record in expected_records:
        if "line_items" not in record or any("uom" not in row for row in record["line_items"]):
            continue
        labeled += 1
        identity = record["document_id"]
        expected = record["line_items"]
        prediction = predicted_by_id.get(identity, {})
        predicted = prediction.get("line_items")
        complete = "line_items" in prediction
        try:
            validate_lines(predicted, expected=False)
        except ValueError:
            predicted = []
            complete = False
        if not complete:
            invalid_documents += 1
        expected_total += len(expected)
        total_fields += sum(len(required_fields(row)) for row in expected)
        for row in expected:
            for field in required_fields(row):
                field_denominators[field] += 1
        predicted_total += len(predicted)
        pairs, ambiguous = _pairs(expected, predicted)
        ambiguous_groups += ambiguous
        missing += len(expected) - len(pairs)
        extra += len(predicted) - len(pairs)
        document_exact = (
            complete and not ambiguous and len(expected) == len(predicted) == len(pairs)
        )
        field_counts, row_count, row_failures = _score_pairs(expected, predicted, pairs)
        matched += sum(field_counts.values())
        for field in field_counts:
            by_field[field] += field_counts[field]
        exact_lines += row_count
        document_exact &= row_count == len(pairs)
        failures.extend({"document_id": identity, **failure} for failure in row_failures)
        if not complete:
            failures.append({"document_id": identity, "kind": "missing_or_invalid_line_output"})
        documents.append(
            {
                "document_id": identity,
                "exact": document_exact,
                "provenance_exact": document_exact
                and all(
                    fields_match(expected[i], predicted[j], required_fields(expected[i]))
                    for i, j in pairs
                ),
            }
        )
    return {
        "status": "measured" if labeled else "not_labeled",
        "alignment_version": ALIGNMENT_VERSION,
        "ambiguous_groups": ambiguous_groups,
        "documents_labeled": labeled,
        "documents_unlabeled": len(expected_records) - labeled,
        "invalid_or_missing_output_documents": invalid_documents,
        "expected_lines": expected_total,
        "predicted_lines": predicted_total,
        "exact_lines": exact_lines,
        "missing_lines": missing,
        "extra_lines": extra,
        "fields_total": total_fields,
        "fields_matched": matched,
        "field_accuracy": round(matched / total_fields, 4) if total_fields else None,
        "by_field": {
            k: round(v / field_denominators[k], 4) if field_denominators[k] else None
            for k, v in by_field.items()
        },
        "precision": round(exact_lines / predicted_total, 4) if predicted_total else None,
        "recall": round(exact_lines / expected_total, 4) if expected_total else None,
        "failures": failures,
        "document_results": documents,
    }


def _score_pairs(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    pairs: list[tuple[int, int]],
) -> tuple[dict[str, int], int, list[dict[str, Any]]]:
    counts = dict.fromkeys(LINE_FIELDS + OPTIONAL_FIELDS, 0)
    exact = 0
    failures: list[dict[str, Any]] = []
    for i, j in pairs:
        a = _normalized(expected[i])
        row_exact = True
        for k, field in enumerate(required_fields(expected[i])):
            try:
                pv = _value(field, predicted[j].get(field))
                correct = field in predicted[j] and a[k] == pv
            except ValueError:
                pv, correct = "<invalid>", False
            counts[field] += int(correct)
            row_exact &= correct
            if not correct:
                failures.append(
                    {
                        "expected_index": i,
                        "predicted_index": j,
                        "field": field,
                        "expected": a[k],
                        "predicted": pv,
                    }
                )
        provenance_exact = fields_match(expected[i], predicted[j], required_fields(expected[i]))
        if not provenance_exact:
            failures.append(
                {"kind": "provenance_mismatch", "expected_index": i, "predicted_index": j}
            )
        exact += int(row_exact and provenance_exact)
    for side, indices in (
        ("missing", set(range(len(expected))) - {i for i, _ in pairs}),
        ("extra", set(range(len(predicted))) - {j for _, j in pairs}),
    ):
        failures.extend({"kind": side, "index": index} for index in sorted(indices))
    return counts, exact, failures
