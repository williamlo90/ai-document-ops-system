from __future__ import annotations

from typing import Any


DEFAULT_REGRESSION_THRESHOLDS = {
    "field_accuracy_drop": 0.02,
    "document_success_rate_drop": 0.05,
    "provider_error_rate_increase": 0.05,
    "average_latency_increase_ratio": 0.25,
    "estimated_cost_increase_ratio": 0.25,
}


def generate_governance_report(
    current_report: dict[str, Any],
    baseline_report: dict[str, Any] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    active_thresholds = {**DEFAULT_REGRESSION_THRESHOLDS, **(thresholds or {})}
    dataset = {
        "name": current_report.get("dataset"),
        "documents_count": current_report.get("documents_count", 0),
        "evidence_level": _evidence_level(int(current_report.get("documents_count", 0))),
        "is_golden_candidate": int(current_report.get("documents_count", 0)) > 0,
    }
    current_metrics = _metric_snapshot(current_report)
    regression = _regression_summary(current_metrics, baseline_report, active_thresholds)
    return {
        "governance_version": "1.0",
        "dataset": dataset,
        "provider": current_report.get("provider"),
        "current": current_metrics,
        "baseline_provider": baseline_report.get("provider") if baseline_report else None,
        "regression": regression,
        "decision_evidence": {
            "field_accuracy": current_metrics["field_accuracy"],
            "document_success_rate": current_metrics["document_success_rate"],
            "provider_error_rate": current_metrics["provider_error_rate"],
            "average_latency_ms": current_metrics["average_latency_ms"],
            "estimated_cost_total": current_metrics["estimated_cost_total"],
        },
        "limitations": _governance_limitations(dataset, current_report),
    }


def _metric_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics", {})
    latency = metrics.get("latency", {})
    cost = metrics.get("cost_estimate") or report.get("cost_estimate") or {}
    return {
        "field_accuracy": float(metrics.get("field_accuracy", 0.0)),
        "document_success_rate": float(metrics.get("document_success_rate", 0.0)),
        "provider_error_rate": float(metrics.get("provider_error_rate", 0.0)),
        "average_latency_ms": float(latency.get("average_ms", 0.0)),
        "estimated_cost_total": cost.get("estimated_cost_total"),
    }


def _regression_summary(
    current: dict[str, Any],
    baseline_report: dict[str, Any] | None,
    thresholds: dict[str, float],
) -> dict[str, Any]:
    if baseline_report is None:
        return {
            "status": "no_baseline",
            "has_regression": False,
            "checks": [],
        }
    baseline = _metric_snapshot(baseline_report)
    checks = [
        _drop_check(
            "field_accuracy",
            baseline["field_accuracy"],
            current["field_accuracy"],
            thresholds["field_accuracy_drop"],
        ),
        _drop_check(
            "document_success_rate",
            baseline["document_success_rate"],
            current["document_success_rate"],
            thresholds["document_success_rate_drop"],
        ),
        _increase_check(
            "provider_error_rate",
            baseline["provider_error_rate"],
            current["provider_error_rate"],
            thresholds["provider_error_rate_increase"],
        ),
        _ratio_increase_check(
            "average_latency_ms",
            baseline["average_latency_ms"],
            current["average_latency_ms"],
            thresholds["average_latency_increase_ratio"],
        ),
        _ratio_increase_check(
            "estimated_cost_total",
            baseline["estimated_cost_total"],
            current["estimated_cost_total"],
            thresholds["estimated_cost_increase_ratio"],
        ),
    ]
    failed = [check for check in checks if check["regressed"]]
    return {
        "status": "regression_detected" if failed else "pass",
        "has_regression": bool(failed),
        "checks": checks,
    }


def _drop_check(
    metric: str,
    baseline: float,
    current: float,
    threshold: float,
) -> dict[str, Any]:
    delta = baseline - current
    return {
        "metric": metric,
        "baseline": baseline,
        "current": current,
        "delta": round(current - baseline, 6),
        "threshold": threshold,
        "regressed": delta > threshold,
    }


def _increase_check(
    metric: str,
    baseline: float,
    current: float,
    threshold: float,
) -> dict[str, Any]:
    delta = current - baseline
    return {
        "metric": metric,
        "baseline": baseline,
        "current": current,
        "delta": round(delta, 6),
        "threshold": threshold,
        "regressed": delta > threshold,
    }


def _ratio_increase_check(
    metric: str,
    baseline: Any,
    current: Any,
    threshold: float,
) -> dict[str, Any]:
    if baseline in (None, 0) or current is None:
        return {
            "metric": metric,
            "baseline": baseline,
            "current": current,
            "delta": None,
            "threshold": threshold,
            "regressed": False,
            "note": "insufficient baseline/current value",
        }
    ratio = (float(current) - float(baseline)) / float(baseline)
    return {
        "metric": metric,
        "baseline": baseline,
        "current": current,
        "delta": round(ratio, 6),
        "threshold": threshold,
        "regressed": ratio > threshold,
    }


def _evidence_level(documents_count: int) -> str:
    if documents_count < 5:
        return "bootstrap"
    if documents_count < 30:
        return "small_golden_set"
    return "expanded_golden_set"


def _governance_limitations(
    dataset: dict[str, Any],
    current_report: dict[str, Any],
) -> list[str]:
    limitations = [
        "Governance results are only as representative as the golden dataset.",
        "Cost values are estimates, not provider billing records.",
        "Latency varies by machine, network, and provider availability.",
    ]
    if dataset["evidence_level"] == "bootstrap":
        limitations.append(
            "Dataset size is bootstrap-level; do not claim production accuracy from this run."
        )
    if "mock" in str(current_report.get("provider", "")):
        limitations.append(
            "Mock provider results validate architecture only and are not real provider performance."
        )
    return limitations
