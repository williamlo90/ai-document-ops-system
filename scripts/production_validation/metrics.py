from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Iterable

from scripts.production_validation.models import (
    AcceptanceThresholds,
    CheckResult,
    RequestSample,
)


def nearest_rank(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if not 0 < percentile <= 100:
        raise ValueError("percentile must be greater than 0 and at most 100")
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    return float(ordered[index])


def summarize_samples(samples: list[RequestSample], *, elapsed_seconds: float) -> dict[str, object]:
    operation_names = sorted({sample.operation for sample in samples})
    operations = {
        operation: _summarize_operation(
            [sample for sample in samples if sample.operation == operation],
            elapsed_seconds=elapsed_seconds,
        )
        for operation in operation_names
    }
    expected = sum(sample.expected_response for sample in samples)
    unexpected_5xx = sum(
        sample.status_code is not None and sample.status_code >= 500 for sample in samples
    )
    total = len(samples)
    return {
        "total_requests": total,
        "expected_responses": expected,
        "unexpected_failures": total - expected,
        "unexpected_5xx": unexpected_5xx,
        "availability_percent": _percent(expected, total),
        "unexpected_5xx_percent": _percent(unexpected_5xx, total),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "throughput_rps": round(total / elapsed_seconds, 3) if elapsed_seconds > 0 else 0.0,
        "operations": operations,
        "timeline": summarize_timeline(samples),
    }


def summarize_timeline(
    samples: list[RequestSample], *, interval_seconds: int = 60
) -> list[dict[str, object]]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    if not samples:
        return []
    parsed = [(sample, _parse_timestamp(sample.started_at)) for sample in samples]
    anchor = min(timestamp for _, timestamp in parsed)
    buckets: dict[int, list[RequestSample]] = {}
    for sample, timestamp in parsed:
        bucket = int((timestamp - anchor).total_seconds() // interval_seconds)
        buckets.setdefault(bucket, []).append(sample)
    timeline = []
    for bucket, bucket_samples in sorted(buckets.items()):
        expected = sum(sample.expected_response for sample in bucket_samples)
        unexpected_5xx = sum(
            sample.status_code is not None and sample.status_code >= 500
            for sample in bucket_samples
        )
        operation_names = sorted({sample.operation for sample in bucket_samples})
        timeline.append(
            {
                "window": bucket,
                "started_at": (anchor + timedelta(seconds=bucket * interval_seconds))
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "count": len(bucket_samples),
                "expected_responses": expected,
                "unexpected_5xx": unexpected_5xx,
                "operations": {
                    operation: _summarize_operation(
                        [sample for sample in bucket_samples if sample.operation == operation],
                        elapsed_seconds=float(interval_seconds),
                    )
                    for operation in operation_names
                },
            }
        )
    return timeline


def evaluate_acceptance(
    summary: dict[str, object], thresholds: AcceptanceThresholds
) -> list[CheckResult]:
    checks = [
        _minimum_check(
            "availability",
            float(summary["availability_percent"]),
            thresholds.availability_percent,
            "%",
        ),
        _maximum_check(
            "unexpected_5xx_rate",
            float(summary["unexpected_5xx_percent"]),
            thresholds.unexpected_5xx_percent,
            "%",
            strict=True,
        ),
    ]
    operations = summary["operations"]
    if not isinstance(operations, dict):
        raise TypeError("summary operations must be a dictionary")
    checks.extend(
        _latency_checks(
            operations,
            "read_invoices",
            {
                "p50_ms": thresholds.read_p50_ms,
                "p95_ms": thresholds.read_p95_ms,
                "p99_ms": thresholds.read_p99_ms,
            },
        )
    )
    checks.extend(
        _latency_checks(
            operations,
            "upload_document",
            {
                "p50_ms": thresholds.upload_p50_ms,
                "p95_ms": thresholds.upload_p95_ms,
                "p99_ms": thresholds.upload_p99_ms,
            },
        )
    )
    return checks


def evaluate_upload_invariants(
    samples: list[RequestSample], *, expected_uploads: int
) -> list[CheckResult]:
    uploads = [sample for sample in samples if sample.operation == "upload_document"]
    successful = [sample for sample in uploads if sample.expected_response]
    document_ids = [sample.document_id for sample in successful if sample.document_id]
    return [
        CheckResult(
            code="upload_schedule_complete",
            passed=len(uploads) == expected_uploads,
            expected=f"{expected_uploads} upload attempts",
            observed=f"{len(uploads)} upload attempts",
            detail="Every scheduled synthetic upload must be attempted.",
        ),
        CheckResult(
            code="upload_ids_present",
            passed=len(document_ids) == len(successful),
            expected="one document ID for every successful upload",
            observed=f"{len(document_ids)} IDs for {len(successful)} successful uploads",
            detail="A successful upload without a document ID cannot be reconciled later.",
        ),
        CheckResult(
            code="upload_ids_unique",
            passed=len(document_ids) == len(set(document_ids)),
            expected="zero duplicate document IDs",
            observed=f"{len(document_ids) - len(set(document_ids))} duplicate IDs",
            detail="Duplicate identifiers indicate an invalid or ambiguous intake result.",
        ),
    ]


def evaluate_document_invariants(
    samples: list[RequestSample], final_states: dict[str, str]
) -> list[CheckResult]:
    uploaded_ids = {
        sample.document_id
        for sample in samples
        if sample.operation == "upload_document" and sample.expected_response and sample.document_id
    }
    converged_states = {"needs_review", "approved", "rejected", "exported"}
    resolved_ids = {
        document_id
        for document_id, status in final_states.items()
        if status in converged_states or status in {"failed", "cancelled"}
    }
    failures = {
        document_id: status
        for document_id, status in final_states.items()
        if status in {"failed", "cancelled"}
    }
    return [
        CheckResult(
            code="uploaded_documents_reconciled",
            passed=uploaded_ids == resolved_ids,
            expected=f"{len(uploaded_ids)} uploaded documents resolved",
            observed=f"{len(resolved_ids)} uploaded documents resolved",
            detail="Every successful upload must be found in a final or review state.",
        ),
        CheckResult(
            code="uploaded_documents_converged",
            passed=all(
                final_states.get(document_id) in converged_states for document_id in uploaded_ids
            ),
            expected="all uploaded documents in a successful final or review state",
            observed=_state_inventory(final_states),
            detail="Queued, processing, failed, cancelled, or unresolved work cannot pass.",
        ),
        CheckResult(
            code="zero_failed_documents",
            passed=not failures,
            expected="0 failed or cancelled documents",
            observed=f"{len(failures)} failed or cancelled documents",
            detail="The deterministic workload must not leave unexplained terminal failures.",
        ),
    ]


def thresholds_as_dict(thresholds: AcceptanceThresholds) -> dict[str, float]:
    return {key: float(value) for key, value in asdict(thresholds).items()}


def _summarize_operation(
    samples: list[RequestSample], *, elapsed_seconds: float
) -> dict[str, object]:
    durations = [sample.duration_ms for sample in samples]
    statuses = Counter(
        str(sample.status_code) if sample.status_code is not None else "transport_error"
        for sample in samples
    )
    expected = sum(sample.expected_response for sample in samples)
    return {
        "count": len(samples),
        "expected_responses": expected,
        "unexpected_failures": len(samples) - expected,
        "status_counts": dict(sorted(statuses.items())),
        "throughput_rps": round(len(samples) / elapsed_seconds, 3) if elapsed_seconds > 0 else 0.0,
        "p50_ms": _rounded_percentile(durations, 50),
        "p90_ms": _rounded_percentile(durations, 90),
        "p95_ms": _rounded_percentile(durations, 95),
        "p99_ms": _rounded_percentile(durations, 99),
        "max_ms": round(max(durations), 3) if durations else None,
    }


def _latency_checks(
    operations: dict[str, object], operation: str, limits: dict[str, float]
) -> list[CheckResult]:
    operation_summary = operations.get(operation)
    if not isinstance(operation_summary, dict):
        return [
            CheckResult(
                code=f"{operation}_samples_present",
                passed=False,
                expected="at least one sample",
                observed="zero samples",
                detail="The workload cannot pass without exercising this operation.",
            )
        ]
    checks: list[CheckResult] = []
    for metric, limit in limits.items():
        value = operation_summary.get(metric)
        if value is None:
            checks.append(
                CheckResult(
                    code=f"{operation}_{metric}",
                    passed=False,
                    expected=f"<= {limit:.3f} ms",
                    observed="no value",
                    detail=f"{operation} {metric} must be measurable.",
                )
            )
        else:
            checks.append(_maximum_check(f"{operation}_{metric}", float(value), limit, "ms"))
    return checks


def _minimum_check(code: str, value: float, minimum: float, unit: str) -> CheckResult:
    return CheckResult(
        code=code,
        passed=value >= minimum,
        expected=f">= {minimum:.3f} {unit}",
        observed=f"{value:.3f} {unit}",
        detail=f"{code} must meet the frozen minimum.",
    )


def _maximum_check(
    code: str, value: float, maximum: float, unit: str, *, strict: bool = False
) -> CheckResult:
    operator = "<" if strict else "<="
    passed = value < maximum if strict else value <= maximum
    return CheckResult(
        code=code,
        passed=passed,
        expected=f"{operator} {maximum:.3f} {unit}",
        observed=f"{value:.3f} {unit}",
        detail=f"{code} must meet the frozen maximum.",
    )


def _percent(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 3) if denominator else 0.0


def _rounded_percentile(values: list[float], percentile: float) -> float | None:
    value = nearest_rank(values, percentile)
    return round(value, 3) if value is not None else None


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("sample timestamp must include a timezone")
    return parsed


def _state_inventory(states: dict[str, str]) -> str:
    counts = Counter(states.values())
    return ", ".join(f"{status}={count}" for status, count in sorted(counts.items())) or "none"
