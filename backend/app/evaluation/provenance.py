"""Compare evidence against independently labeled source anchors, never mere coverage."""

from typing import Any


def evidence_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    kind = value.get("kind")
    source = (
        type(value.get("page")) is int
        and value["page"] > 0
        and isinstance(value.get("excerpt"), str)
        and bool(value["excerpt"].strip())
    )
    if kind == "observed":
        return bool(source)
    if kind == "normalized":
        return bool(source and value.get("transform"))
    if kind == "derived":
        return bool(
            value.get("formula")
            and isinstance(value.get("inputs"), list)
            and value["inputs"]
            and all(isinstance(i, str) and i for i in value["inputs"])
        )
    if kind == "corrected":
        return bool(source and all(value.get(k) for k in ("actor", "time", "reason")))
    return False


def evidence_matches(expected: Any, predicted: Any) -> bool:
    # The oracle specifies acceptable anchor/transform; additional runtime metadata is allowed.
    return (
        evidence_valid(expected)
        and evidence_valid(predicted)
        and all(predicted.get(k) == v for k, v in expected.items())
    )


def field_evidence(record: dict, field: str) -> Any:
    evidence = record.get("provenance")
    return evidence.get(field) if isinstance(evidence, dict) else None


def fields_have_labels(record: dict, fields: tuple[str, ...]) -> bool:
    return all(
        f in record and (record[f] is None or evidence_valid(field_evidence(record, f)))
        for f in fields
    )


def fields_match(record: dict, prediction: dict, fields: tuple[str, ...]) -> bool:
    return all(
        record.get(f) is None
        or evidence_matches(field_evidence(record, f), field_evidence(prediction, f))
        for f in fields
    )
