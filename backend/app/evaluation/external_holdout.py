from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

from app.evaluation.invoice import (
    EVALUATED_FIELDS,
    evaluate_invoices,
    report_to_dict,
    validate_record_ids,
)


def build_external_evaluation_summary(
    expected_records: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    *,
    split: str,
    provider: str,
    dataset_class: str = "external licensed synthetic invoices",
) -> dict[str, Any]:
    validate_record_ids(expected_records, "Expected")
    validate_record_ids(observations, "Observation")
    expected_ids = {record["document_id"] for record in expected_records}
    if any(item["document_id"] not in expected_ids for item in observations):
        raise ValueError("Observation document_id is not in the expected manifest")
    successful_observations = [item for item in observations if _extraction_completed(item)]
    predicted_records = [
        {**item["predicted_fields"], "document_id": item["document_id"]}
        for item in successful_observations
    ]
    field_report = report_to_dict(evaluate_invoices(expected_records, predicted_records))
    observed_by_id = {str(item["document_id"]): item for item in observations}
    predicted_by_id = {str(item["document_id"]): item for item in predicted_records}
    document_exact = _document_exact_matches(expected_records, predicted_by_id)
    validation_exact, blocker_exact = _validation_metrics(expected_records, observed_by_id)
    evidence = _evidence_metrics(expected_records, observed_by_id, predicted_by_id)
    validation_total = sum("expected_validation_codes" in item for item in expected_records)
    completed_validations = sum(_validation_completed(item) for item in observations)

    return {
        "report_version": "2.1",
        "evaluation_input": "original_provider_extraction",
        "legacy_metric_scope": "header_only",
        "dataset_class": dataset_class,
        "split": split,
        "provider": provider,
        "documents_count": len(expected_records),
        "provider_errors": sum(1 for item in observations if item.get("error")),
        "metrics": {
            **_quality_metrics(field_report),
            "provider_success_rate": _ratio(len(successful_observations), len(expected_records)),
            "documents_succeeded": len(successful_observations),
            "documents_incomplete": len(expected_records) - len(successful_observations),
            "validation_documents_total": validation_total,
            "validation_documents_completed": completed_validations,
            "validation_completion_rate": _ratio(completed_validations, len(expected_records)),
            "field_accuracy": field_report["field_accuracy"],
            "fields_matched": field_report["fields_matched"],
            "fields_total": field_report["fields_total"],
            "by_field": field_report["by_field"],
            "document_exact_match_rate": _ratio(document_exact, len(expected_records)),
            "validation_code_exact_match_rate": _ratio(validation_exact, validation_total),
            "approval_blocker_accuracy": _ratio(blocker_exact, validation_total),
            **evidence,
            "conditional_on_provider_success": _conditional_metrics(
                expected_records,
                predicted_records,
                observed_by_id,
                evidence,
            ),
            "duplicate_detection": _duplicate_metrics(expected_records, predicted_by_id),
            "latency_ms": _latency_metrics(observations),
        },
        "failure_taxonomy": _failure_taxonomy(
            expected_records,
            observed_by_id,
            predicted_by_id,
        ),
        "limitations": [
            f"Dataset class: {dataset_class}; results apply only to this manifest.",
            "Results measure this fixed manifest and do not establish global accuracy.",
            "Legacy field_accuracy and document_exact_match_rate measure headers only.",
            "Full-invoice accuracy is measured only on records with complete header, line and provenance labels.",
            "Source-evidence coverage requires both a page reference and an exact source excerpt.",
            "Duplicate recall is not measured when the split contains no labeled duplicate pair.",
            "Provider latency depends on the local network and hosted API conditions during the run.",
        ],
    }


def _quality_metrics(report: dict[str, Any]) -> dict[str, Any]:
    # Aggregate reports must not leak invoice values or document IDs.
    return {
        key: value for key, value in report.items() if key.startswith(("header_", "full_invoice_"))
    } | {
        "line_items": {
            key: value for key, value in report["line_items"].items() if key != "failures"
        }
    }


def _extraction_completed(observation: dict[str, Any]) -> bool:
    return (
        bool(observation)
        and not observation.get("error")
        and isinstance(observation.get("predicted_fields"), dict)
        and bool(observation["predicted_fields"])
    )


def _validation_completed(observation: dict[str, Any]) -> bool:
    return (
        _extraction_completed(observation)
        and observation.get("validation_completed") is not False
        and isinstance(observation.get("predicted_validation_codes"), list)
        and all(isinstance(code, str) for code in observation["predicted_validation_codes"])
    )


def _document_exact_matches(
    expected_records: list[dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> int:
    count = 0
    for expected in expected_records:
        predicted = predicted_by_id.get(str(expected["document_id"]))
        predictions = [predicted] if predicted is not None else []
        single = report_to_dict(evaluate_invoices([expected], predictions))
        if single["fields_matched"] == single["fields_total"]:
            count += 1
    return count


def _validation_metrics(
    expected_records: list[dict[str, Any]],
    observed_by_id: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    validation_exact = 0
    blocker_exact = 0
    for expected in expected_records:
        observed = observed_by_id.get(str(expected["document_id"]), {})
        if "expected_validation_codes" not in expected:
            continue
        if not isinstance(expected["expected_validation_codes"], list) or not all(
            isinstance(code, str) for code in expected["expected_validation_codes"]
        ):
            raise ValueError("expected_validation_codes must be a list of strings")
        if not _validation_completed(observed):
            continue
        expected_codes = set(expected.get("expected_validation_codes") or [])
        predicted_codes = set(observed.get("predicted_validation_codes") or [])
        if expected_codes == predicted_codes:
            validation_exact += 1
        expected_blocked = expected.get("expected_approval_blocked", bool(expected_codes))
        predicted_blocked = observed.get("predicted_approval_blocked", bool(predicted_codes))
        if expected_blocked == predicted_blocked:
            blocker_exact += 1
    return validation_exact, blocker_exact


def _evidence_metrics(
    expected_records: list[dict[str, Any]],
    observed_by_id: dict[str, dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    correct_non_null = 0
    with_confidence = 0
    with_source_evidence = 0
    for expected in expected_records:
        document_id = str(expected["document_id"])
        predicted = predicted_by_id.get(document_id)
        observed = observed_by_id.get(document_id, {})
        confidence_fields = set(observed.get("confidence_fields") or [])
        evidence_fields = set(observed.get("evidence_fields") or [])
        for field_name in EVALUATED_FIELDS:
            if expected.get(field_name) in (None, ""):
                continue
            predictions = [predicted] if predicted is not None else []
            report = report_to_dict(evaluate_invoices([expected], predictions))
            failures = {failure["field_name"] for failure in report["failures"]}
            if field_name in failures:
                continue
            correct_non_null += 1
            if field_name in confidence_fields:
                with_confidence += 1
            if field_name in evidence_fields:
                with_source_evidence += 1
    return {
        "confidence_metadata_coverage": _ratio(with_confidence, correct_non_null),
        "source_evidence_coverage": _ratio(with_source_evidence, correct_non_null),
        "correct_non_null_fields": correct_non_null,
    }


def _duplicate_metrics(
    expected_records: list[dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected_pairs = _expected_duplicate_pairs(expected_records)
    predicted_pairs = _predicted_duplicate_pairs(expected_records, predicted_by_id)
    true_positive = len(expected_pairs & predicted_pairs)
    false_positive = len(predicted_pairs - expected_pairs)
    false_negative = len(expected_pairs - predicted_pairs)
    if not expected_pairs:
        status = "not_measured_no_positive_pairs"
    else:
        status = "measured"
    return {
        "status": status,
        "positive_pairs_expected": len(expected_pairs),
        "true_positive_pairs": true_positive,
        "false_positive_pairs": false_positive,
        "false_negative_pairs": false_negative,
        "precision": _ratio_or_none(true_positive, true_positive + false_positive),
        "recall": _ratio_or_none(true_positive, true_positive + false_negative),
    }


def _expected_duplicate_pairs(expected_records: list[dict[str, Any]]) -> set[frozenset[str]]:
    groups: dict[str, list[str]] = {}
    for record in expected_records:
        group = record.get("duplicate_group")
        if group:
            groups.setdefault(str(group), []).append(str(record["document_id"]))
    return {
        frozenset(pair) for members in groups.values() for pair in combinations(sorted(members), 2)
    }


def _predicted_duplicate_pairs(
    expected_records: list[dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> set[frozenset[str]]:
    groups: dict[tuple[str, str], list[str]] = {}
    for expected in expected_records:
        document_id = str(expected["document_id"])
        predicted = predicted_by_id.get(document_id, {})
        identity = _identity(predicted.get("vendor_name"), predicted.get("invoice_number"))
        if identity is not None:
            groups.setdefault(identity, []).append(document_id)
    return {
        frozenset(pair) for members in groups.values() for pair in combinations(sorted(members), 2)
    }


def _identity(vendor: Any, number: Any) -> tuple[str, str] | None:
    normalized_vendor = _identity_text(vendor)
    normalized_number = _identity_text(number)
    if not normalized_vendor or not normalized_number:
        return None
    return normalized_vendor, normalized_number


def _identity_text(value: Any) -> str:
    return "".join(character for character in str(value or "").casefold() if character.isalnum())


def _failure_taxonomy(
    expected_records: list[dict[str, Any]],
    observed_by_id: dict[str, dict[str, Any]],
    predicted_by_id: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for expected in expected_records:
        document_id = str(expected["document_id"])
        observed = observed_by_id.get(document_id, {})
        predicted = predicted_by_id.get(document_id)
        predicted_fields = predicted or {}
        if observed.get("error"):
            counts["provider_error"] += 1
        if predicted is None:
            counts["unscored_fields_due_to_provider_error"] += len(EVALUATED_FIELDS)
        else:
            report = report_to_dict(evaluate_invoices([expected], [predicted]))
            for failure in report["failures"]:
                if failure["expected"] is None and failure["predicted"] is not None:
                    counts["hallucinated_value"] += 1
                elif failure["expected"] is not None and failure["predicted"] is None:
                    counts["missing_value"] += 1
                else:
                    counts["incorrect_value"] += 1
        expected_codes = set(expected.get("expected_validation_codes") or [])
        predicted_codes = set(observed.get("predicted_validation_codes") or [])
        if not _validation_completed(observed):
            counts["validation_incomplete"] += 1
        elif expected_codes != predicted_codes:
            counts["validation_code_mismatch"] += 1
        counts["missing_source_evidence"] += _missing_evidence_count(predicted_fields, observed)
    return dict(sorted(counts.items()))


def _latency_metrics(observations: list[dict[str, Any]]) -> dict[str, float]:
    values = [float(item.get("latency_ms") or 0.0) for item in observations]
    if not values:
        return {"average": 0.0, "minimum": 0.0, "maximum": 0.0}
    return {
        "average": round(sum(values) / len(values), 2),
        "minimum": round(min(values), 2),
        "maximum": round(max(values), 2),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _ratio_or_none(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _missing_evidence_count(predicted: dict[str, Any], observed: dict[str, Any]) -> int:
    evidence = set(observed.get("evidence_fields") or [])
    return sum(
        predicted.get(field) not in (None, "") and field not in evidence
        for field in EVALUATED_FIELDS
    )


def _conditional_metrics(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    observations: dict[str, dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    by_id = {item["document_id"]: item for item in predicted}
    subset = [item for item in expected if item["document_id"] in by_id]
    report = report_to_dict(evaluate_invoices(subset, predicted))
    validation, blockers = _validation_metrics(subset, observations)
    total = sum("expected_validation_codes" in item for item in subset)
    return {
        **_quality_metrics(report),
        "documents_count": len(subset),
        "validation_documents_total": total,
        "field_accuracy": report["field_accuracy"],
        "document_exact_match_rate": _ratio(_document_exact_matches(subset, by_id), len(subset)),
        "validation_code_exact_match_rate": _ratio(validation, total),
        "approval_blocker_accuracy": _ratio(blockers, total),
        "confidence_metadata_coverage": evidence["confidence_metadata_coverage"],
        "source_evidence_coverage": evidence["source_evidence_coverage"],
    }
