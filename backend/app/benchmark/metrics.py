from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.benchmark.models import BenchmarkRun, run_results_to_predicted_records
from app.benchmark.pricing import get_cost_estimate
from app.evaluation.invoice import EvaluationReport, evaluate_invoices, report_to_dict


@dataclass(frozen=True)
class LatencyMetrics:
    total_ms: float
    average_ms: float
    min_ms: float
    max_ms: float


@dataclass(frozen=True)
class BenchmarkMetrics:
    evaluation: EvaluationReport
    document_success_rate: float
    documents_succeeded: int
    documents_failed: int
    provider_error_rate: float
    missing_field_rate: float
    invalid_schema_rate: float
    latency: LatencyMetrics
    cost_estimate: dict[str, Any]


def calculate_benchmark_metrics(
    run: BenchmarkRun,
    expected_records: list[dict[str, Any]],
) -> BenchmarkMetrics:
    predicted_records = run_results_to_predicted_records(run.results)
    evaluation = evaluate_invoices(expected_records, predicted_records)
    expected_ids = {str(record["document_id"]) for record in expected_records}
    success_ids = _successful_document_ids(evaluation, run, expected_ids)
    provider_error_count = sum(1 for result in run.results if result.error is not None)
    missing_field_count = sum(1 for failure in evaluation.failures if failure.predicted is None)
    invalid_schema_count = provider_error_count
    total_latency_ms = sum(result.latency_ms for result in run.results)

    return BenchmarkMetrics(
        evaluation=evaluation,
        document_success_rate=_ratio(len(success_ids), len(expected_ids)),
        documents_succeeded=len(success_ids),
        documents_failed=max(len(expected_ids) - len(success_ids), 0),
        provider_error_rate=_ratio(provider_error_count, len(run.results)),
        missing_field_rate=_ratio(missing_field_count, evaluation.fields_total),
        invalid_schema_rate=_ratio(invalid_schema_count, len(run.results)),
        latency=_latency_metrics(tuple(result.latency_ms for result in run.results)),
        cost_estimate=get_cost_estimate(run.provider_name, len(run.results), total_latency_ms),
    )


def benchmark_metrics_to_dict(metrics: BenchmarkMetrics) -> dict[str, Any]:
    evaluation = report_to_dict(metrics.evaluation)
    return {
        **evaluation,
        "document_success_rate": round(metrics.document_success_rate, 4),
        "documents_succeeded": metrics.documents_succeeded,
        "documents_failed": metrics.documents_failed,
        "provider_error_rate": round(metrics.provider_error_rate, 4),
        "missing_field_rate": round(metrics.missing_field_rate, 4),
        "invalid_schema_rate": round(metrics.invalid_schema_rate, 4),
        "latency": {
            "total_ms": round(metrics.latency.total_ms, 2),
            "average_ms": round(metrics.latency.average_ms, 2),
            "min_ms": round(metrics.latency.min_ms, 2),
            "max_ms": round(metrics.latency.max_ms, 2),
        },
        "cost_estimate": metrics.cost_estimate,
    }


def _successful_document_ids(
    evaluation: EvaluationReport,
    run: BenchmarkRun,
    expected_ids: set[str],
) -> set[str]:
    failed_ids = {failure.document_id for failure in evaluation.failures}
    failed_ids.update(result.document_id for result in run.results if result.error is not None)
    evaluated_ids = {result.document_id for result in run.results}
    return (evaluated_ids & expected_ids) - failed_ids


def _latency_metrics(values: tuple[float, ...]) -> LatencyMetrics:
    if not values:
        return LatencyMetrics(total_ms=0.0, average_ms=0.0, min_ms=0.0, max_ms=0.0)
    total = sum(values)
    return LatencyMetrics(
        total_ms=total,
        average_ms=total / len(values),
        min_ms=min(values),
        max_ms=max(values),
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
