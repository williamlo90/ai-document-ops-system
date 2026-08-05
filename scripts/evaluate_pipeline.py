from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.evaluation.invoice import evaluate_invoices, report_to_dict  # noqa: E402


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    if len(sys.argv) not in {3, 4}:
        raise SystemExit(
            "Usage: python scripts/evaluate_pipeline.py expected.json admin-token [base-url]"
        )
    expected_path = Path(sys.argv[1])
    admin_token = sys.argv[2]
    base_url = sys.argv[3] if len(sys.argv) == 4 else DEFAULT_BASE_URL
    expected = _load_records(expected_path)
    predicted = _fetch_predictions(base_url, admin_token)
    metrics = _fetch_metrics(base_url, admin_token)
    report = report_to_dict(evaluate_invoices(expected, predicted))
    report["validation_failure_rate"] = _validation_failure_rate(metrics)
    report["average_processing_time_ms"] = metrics.get("average_processing_time_ms", 0.0)
    report["estimated_cost_per_document_usd"] = 0.05
    print(json.dumps(report, indent=2))


def _load_records(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data


def _fetch_predictions(base_url: str, admin_token: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/exports/predictions.json",
        headers={"X-Admin-Token": admin_token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode())
    if not isinstance(data, list):
        raise ValueError("Prediction export must return a JSON list")
    return data


def _fetch_metrics(base_url: str, admin_token: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/metrics/summary",
        headers={"X-Admin-Token": admin_token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def _validation_failure_rate(metrics: dict[str, object]) -> float:
    by_status = metrics.get("by_status", {})
    if not isinstance(by_status, dict):
        return 0.0
    needs_review = int(by_status.get("needs_review", 0) or 0)
    rejected = int(by_status.get("rejected", 0) or 0)
    approved = int(by_status.get("approved", 0) or 0)
    exported = int(by_status.get("exported", 0) or 0)
    total = needs_review + rejected + approved + exported
    return (needs_review + rejected) / total if total else 0.0


if __name__ == "__main__":
    main()
