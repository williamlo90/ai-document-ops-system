from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "evidence"
HOLDOUT_REPORT_PATTERN = "external-invoice-*-holdout-final.json"


def load_latest_provider_cost_summary(
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
) -> dict[str, object]:
    reports = [_read_report(path) for path in evidence_dir.glob(HOLDOUT_REPORT_PATTERN)]
    valid_reports = [report for report in reports if report is not None]
    if not valid_reports:
        return {
            "available": False,
            "message": "No sealed external evaluation cost report is available yet.",
        }

    report = max(valid_reports, key=lambda item: str(item.get("generated_at") or ""))
    economics = _mapping(report.get("provider_economics"))
    usage = _mapping(economics.get("usage"))
    attempts = _mapping(economics.get("attempts"))
    cost = _mapping(economics.get("cost"))
    pricing = _mapping(economics.get("pricing_snapshot"))
    documents_count = _integer(report.get("documents_count"))
    total_cost = _number(cost.get("estimated_total_usd"))
    ocr_cost = _number(cost.get("ocr_usd"))
    extractor_cost = sum(
        _number(cost.get(key)) or 0.0
        for key in (
            "extractor_input_usd",
            "extractor_cached_input_usd",
            "extractor_output_usd",
        )
    )

    return {
        "available": True,
        "dataset_class": report.get("dataset_class"),
        "split": report.get("split"),
        "documents_count": documents_count,
        "generated_at": report.get("generated_at"),
        "holdout_seal_verified": bool(report.get("holdout_seal_verified")),
        "currency": pricing.get("currency") or "USD",
        "pricing_effective_date": pricing.get("effective_date"),
        "estimate_status": cost.get("status"),
        "estimated_total_usd": total_cost,
        "estimated_per_document_usd": (
            round(total_cost / documents_count, 6)
            if total_cost is not None and documents_count
            else None
        ),
        "ocr": {
            "provider": "Mistral",
            "model": cost.get("parser_model"),
            "pages_processed": _integer(usage.get("ocr_pages_processed")),
            "estimated_cost_usd": ocr_cost,
        },
        "extraction": {
            "provider": "OpenAI",
            "model": cost.get("extractor_model"),
            "input_tokens": _integer(usage.get("extractor_input_tokens")),
            "cached_input_tokens": _integer(usage.get("extractor_cached_input_tokens")),
            "output_tokens": _integer(usage.get("extractor_output_tokens")),
            "total_tokens": _integer(usage.get("extractor_total_tokens")),
            "estimated_cost_usd": round(extractor_cost, 6),
        },
        "attempts": {
            "total": _integer(attempts.get("total")),
            "succeeded": _integer(attempts.get("succeeded")),
            "failed": _integer(attempts.get("failed")),
        },
        "claim_boundary": cost.get("claim_boundary"),
    }


def _read_report(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not value.get("holdout_seal_verified"):
        return None
    if not isinstance(value.get("provider_economics"), dict):
        return None
    return value


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    if isinstance(value, bool):
        return 0
    return int(value) if isinstance(value, (int, float)) else 0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
