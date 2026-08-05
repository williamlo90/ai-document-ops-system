from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.benchmark.metrics import (
    BenchmarkMetrics,
    benchmark_metrics_to_dict,
    calculate_benchmark_metrics,
)
from app.benchmark.models import BenchmarkRun
from app.evaluation.invoice import (
    EvaluationReport,
)


def generate_json_report(
    run: BenchmarkRun,
    dataset_records: list[dict[str, Any]],
    evaluation: EvaluationReport | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    metrics = _metrics(run, dataset_records, evaluation)
    metrics_dict = benchmark_metrics_to_dict(metrics)
    report: dict[str, Any] = {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": run.dataset_name,
        "provider": run.provider_name,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "documents_count": len(run.results),
        "documents_with_errors": sum(1 for r in run.results if r.error is not None),
        "metrics": metrics_dict,
        "cost_estimate": metrics.cost_estimate,
    }
    if verbose:
        report["results"] = [
            {
                "document_id": r.document_id,
                "latency_ms": round(r.latency_ms, 2),
                "error": r.error,
            }
            for r in run.results
        ]
    return report


def generate_comparison_json_report(
    runs: list[BenchmarkRun],
    dataset_records: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_reports = [_provider_summary(run, dataset_records) for run in runs]
    return generate_comparison_json_report_from_provider_summaries(
        dataset=runs[0].dataset_name if runs else None,
        provider_reports=provider_reports,
        limitations=_limitations(runs),
    )


def generate_comparison_json_report_from_provider_summaries(
    dataset: str | None,
    provider_reports: list[dict[str, Any]],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "providers_count": len(provider_reports),
        "ranking": _rank_providers(provider_reports),
        "providers": provider_reports,
        "decision": _decision_summary(provider_reports),
        "limitations": limitations or _limitations_from_provider_reports(provider_reports),
    }


def generate_comparison_markdown_report(
    runs: list[BenchmarkRun],
    dataset_records: list[dict[str, Any]],
) -> str:
    report = generate_comparison_json_report(runs, dataset_records)
    lines = [
        f"# Provider Benchmark Comparison: {report['dataset'] or 'No dataset'}",
        "",
        "## Provider Ranking",
        "",
        "| Rank | Provider | Field Accuracy | Document Success | Avg Latency | Est. Cost | Errors |",
        "|------|----------|----------------|------------------|-------------|-----------|--------|",
    ]
    for ranked in report["ranking"]:
        lines.append(
            "| {rank} | {provider} | {field_accuracy:.2%} | {document_success_rate:.2%} | "
            "{average_latency_ms:.0f} ms | ${estimated_cost_total} | {provider_error_rate:.2%} |".format(
                **ranked
            )
        )

    decision = report["decision"]
    if decision["recommended_provider"]:
        lines.extend(
            [
                "",
                "## Decision Summary",
                "",
                f"**Recommended provider:** {decision['recommended_provider']}",
                f"**Decision score:** {decision['decision_score']:.2f}",
                "",
                "### Why",
                "",
                *[f"- {item}" for item in decision["reasons"]],
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Provider Details",
            "",
        ]
    )
    for provider in report["providers"]:
        lines.extend(
            [
                f"### {provider['provider']}",
                "",
                f"- Field accuracy: {provider['field_accuracy']:.2%}",
                f"- Document success rate: {provider['document_success_rate']:.2%}",
                f"- Missing field rate: {provider['missing_field_rate']:.2%}",
                f"- Provider error rate: {provider['provider_error_rate']:.2%}",
                f"- Average latency: {provider['average_latency_ms']:.0f} ms",
                f"- Estimated total cost: ${provider['estimated_cost_total']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Known Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
        ]
    )
    return "\n".join(lines)


def generate_markdown_report(
    run: BenchmarkRun,
    dataset_records: list[dict[str, Any]],
    evaluation: EvaluationReport | None = None,
    verbose: bool = False,
) -> str:
    metrics = benchmark_metrics_to_dict(_metrics(run, dataset_records, evaluation))
    cost = metrics["cost_estimate"]

    lines = [
        f"# Benchmark Report: {run.dataset_name}",
        "",
        f"**Provider:** {run.provider_name}",
        f"**Documents:** {len(run.results)} ({metrics['documents_total']} evaluated, {sum(1 for r in run.results if r.error is not None)} with errors)",
        f"**Duration:** {run.started_at.isoformat()} — {run.finished_at.isoformat()}",
        "",
        "## Accuracy",
        "",
        f"- **Field accuracy:** {metrics['field_accuracy']:.2%}",
        f"- **Document success rate:** {metrics['document_success_rate']:.2%}",
        f"- **Fields matched:** {metrics['fields_matched']} / {metrics['fields_total']}",
        f"- **Missing field rate:** {metrics['missing_field_rate']:.2%}",
        f"- **Provider error rate:** {metrics['provider_error_rate']:.2%}",
    ]

    lines.append("")
    lines.append("### Per-Field Accuracy")
    lines.append("")
    lines.append("| Field | Accuracy |")
    lines.append("|-------|----------|")
    for field, acc in metrics["by_field"].items():
        lines.append(f"| {field} | {acc:.2%} |")

    lines.append("")
    lines.append("## Cost Estimate")
    lines.append("")
    lines.append(f"- **Per document:** ${cost['estimated_cost_per_document']}")
    lines.append(f"- **Total estimated:** ${cost['estimated_cost_total']}")

    lines.append("")
    lines.append("## Latency")
    lines.append("")
    lines.append(f"- **Total:** {metrics['latency']['total_ms']:.0f} ms")
    lines.append(f"- **Average per document:** {metrics['latency']['average_ms']:.0f} ms")
    lines.append(
        f"- **Min / max:** {metrics['latency']['min_ms']:.0f} ms / {metrics['latency']['max_ms']:.0f} ms"
    )

    if metrics["failures"]:
        lines.append("")
        lines.append("## Field Failures")
        lines.append("")
        lines.append("| Document ID | Field | Expected | Predicted |")
        lines.append("|-------------|-------|----------|-----------|")
        for failure in metrics["failures"]:
            exp = failure["expected"] or "(empty)"
            pred = failure["predicted"] or "(empty)"
            lines.append(f"| {failure['document_id']} | {failure['field_name']} | {exp} | {pred} |")

    if "mock" in run.provider_name:
        lines.append("")
        lines.append(
            "> **Note:** This report was generated using mock providers with synthetic data. "
            "Results are for architecture validation only, not real provider comparison."
        )

    lines.append("")
    return "\n".join(lines)


def _metrics(
    run: BenchmarkRun,
    dataset_records: list[dict[str, Any]],
    evaluation: EvaluationReport | None,
) -> BenchmarkMetrics:
    if evaluation is None:
        return calculate_benchmark_metrics(run, dataset_records)
    metrics = calculate_benchmark_metrics(run, dataset_records)
    return BenchmarkMetrics(
        evaluation=evaluation,
        document_success_rate=metrics.document_success_rate,
        documents_succeeded=metrics.documents_succeeded,
        documents_failed=metrics.documents_failed,
        provider_error_rate=metrics.provider_error_rate,
        missing_field_rate=metrics.missing_field_rate,
        invalid_schema_rate=metrics.invalid_schema_rate,
        latency=metrics.latency,
        cost_estimate=metrics.cost_estimate,
    )


def _provider_summary(run: BenchmarkRun, dataset_records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = benchmark_metrics_to_dict(calculate_benchmark_metrics(run, dataset_records))
    return {
        "provider": run.provider_name,
        "provider_mode": "mock" if "mock" in run.provider_name else "real",
        "documents_count": len(run.results),
        "field_accuracy": metrics["field_accuracy"],
        "document_success_rate": metrics["document_success_rate"],
        "missing_field_rate": metrics["missing_field_rate"],
        "provider_error_rate": metrics["provider_error_rate"],
        "invalid_schema_rate": metrics["invalid_schema_rate"],
        "average_latency_ms": metrics["latency"]["average_ms"],
        "estimated_cost_total": metrics["cost_estimate"]["estimated_cost_total"],
        "estimated_cost_per_document": metrics["cost_estimate"]["estimated_cost_per_document"],
        "failure_examples": _failure_examples(metrics),
        "provider_errors": _provider_errors(run),
    }


def _provider_errors(run: BenchmarkRun, limit: int = 5) -> list[dict[str, str]]:
    errors = []
    for result in run.results:
        if result.error is None:
            continue
        errors.append(
            {
                "document_id": result.document_id,
                "error": result.error,
                "trace_id": result.trace_id or "",
            }
        )
        if len(errors) >= limit:
            break
    return errors


def _failure_examples(metrics: dict[str, Any], limit: int = 6) -> list[dict[str, str]]:
    examples = []
    for failure in metrics["failures"][:limit]:
        examples.append(
            {
                "document_id": str(failure["document_id"]),
                "field_name": str(failure["field_name"]),
                "expected": _display_value(failure.get("expected")),
                "predicted": _display_value(failure.get("predicted")),
            }
        )
    return examples


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "(empty)"
    return str(value)


def _rank_providers(provider_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        provider_reports,
        key=lambda item: (
            -item["document_success_rate"],
            -item["field_accuracy"],
            item["provider_error_rate"],
            (
                item["estimated_cost_total"]
                if item["estimated_cost_total"] is not None
                else float("inf")
            ),
            item["average_latency_ms"],
        ),
    )
    return [
        {
            "rank": index,
            **item,
        }
        for index, item in enumerate(ranked, start=1)
    ]


def _decision_summary(provider_reports: list[dict[str, Any]]) -> dict[str, Any]:
    scored = _score_providers(provider_reports)
    if not scored:
        return {
            "recommended_provider": None,
            "decision_score": 0.0,
            "scoring_weights": _scoring_weights(),
            "reasons": ["No provider results are available."],
            "providers": [],
        }
    winner = scored[0]
    return {
        "recommended_provider": winner["provider"],
        "decision_score": winner["decision_score"],
        "scoring_weights": _scoring_weights(),
        "reasons": _decision_reasons(winner, len(scored)),
        "providers": scored,
    }


def _score_providers(provider_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cost_values = [
        float(item["estimated_cost_total"])
        for item in provider_reports
        if item.get("estimated_cost_total") is not None
    ]
    latency_values = [
        float(item["average_latency_ms"])
        for item in provider_reports
        if item.get("average_latency_ms") is not None
    ]
    scored = []
    for item in provider_reports:
        cost_score = _inverse_normalized_optional(item.get("estimated_cost_total"), cost_values)
        latency_score = _inverse_normalized_optional(item.get("average_latency_ms"), latency_values)
        reliability_score = 1 - float(item["provider_error_rate"])
        score = (
            0.40 * float(item["document_success_rate"])
            + 0.30 * float(item["field_accuracy"])
            + 0.15 * reliability_score
            + 0.10 * cost_score
            + 0.05 * latency_score
        )
        scored.append(
            {
                **item,
                "decision_score": round(score, 4),
                "cost_score": round(cost_score, 4),
                "latency_score": round(latency_score, 4),
                "reliability_score": round(reliability_score, 4),
            }
        )
    return sorted(
        scored,
        key=lambda item: (
            -item["decision_score"],
            -item["document_success_rate"],
            -item["field_accuracy"],
            (
                item["estimated_cost_total"]
                if item["estimated_cost_total"] is not None
                else float("inf")
            ),
            item["average_latency_ms"],
            item["provider"],
        ),
    )


def _inverse_normalized(value: float, values: list[float]) -> float:
    if not values:
        return 1.0
    low = min(values)
    high = max(values)
    if high == low:
        return 1.0
    return 1 - ((value - low) / (high - low))


def _inverse_normalized_optional(value: Any, values: list[float]) -> float:
    if value is None:
        return 0.0
    return _inverse_normalized(float(value), values)


def _scoring_weights() -> dict[str, float]:
    return {
        "document_success_rate": 0.40,
        "field_accuracy": 0.30,
        "reliability": 0.15,
        "cost": 0.10,
        "latency": 0.05,
    }


def _decision_reasons(winner: dict[str, Any], provider_count: int) -> list[str]:
    reasons = [
        f"Ranks highest by weighted decision score across {provider_count} provider result(s).",
        f"Document success rate: {winner['document_success_rate']:.2%}.",
        f"Field accuracy: {winner['field_accuracy']:.2%}.",
        f"Provider error rate: {winner['provider_error_rate']:.2%}.",
    ]
    if winner.get("estimated_cost_total") is not None:
        reasons.append(f"Estimated total cost: ${winner['estimated_cost_total']}.")
    reasons.append(f"Average latency: {winner['average_latency_ms']:.0f} ms.")
    return reasons


def _limitations(runs: list[BenchmarkRun]) -> list[str]:
    limitations = [
        "This benchmark reflects the provided fixture dataset, not global production accuracy.",
        "Cost values are estimates from static pricing configuration, not live billing data.",
        "Latency is measured from local benchmark execution and may vary across networks and machines.",
        "Line-item matching and layout/bounding-box accuracy are out of scope for this report.",
    ]
    if any(run.provider_name.startswith("mock") or "mock" in run.provider_name for run in runs):
        limitations.append(
            "Mock provider results validate architecture only and should not be treated as real provider performance."
        )
    return limitations


def _limitations_from_provider_reports(provider_reports: list[dict[str, Any]]) -> list[str]:
    limitations = [
        "This benchmark reflects the provided fixture dataset, not global production accuracy.",
        "Cost values are estimates from static pricing configuration, not live billing data.",
        "Latency is measured from local benchmark execution and may vary across networks and machines.",
        "Line-item matching and layout/bounding-box accuracy are out of scope for this report.",
    ]
    if any("mock" in str(provider.get("provider", "")) for provider in provider_reports):
        limitations.append(
            "Mock provider results validate architecture only and should not be treated as real provider performance."
        )
    return limitations
