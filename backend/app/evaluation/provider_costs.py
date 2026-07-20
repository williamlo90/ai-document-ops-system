from __future__ import annotations

from collections import Counter
from typing import Any


PRICING_SNAPSHOT = {
    "effective_date": "2026-07-20",
    "currency": "USD",
    "sources": {
        "openai": "https://developers.openai.com/api/docs/models/gpt-5.4-mini",
        "mistral": "https://docs.mistral.ai/models/model-cards/ocr-4-0",
    },
    "extractor": {
        "gpt-5.4-mini": {
            "input_per_million_tokens": 0.75,
            "cached_input_per_million_tokens": 0.075,
            "output_per_million_tokens": 4.50,
        },
        "gpt-5.4-mini-2026-03-17": {
            "input_per_million_tokens": 0.75,
            "cached_input_per_million_tokens": 0.075,
            "output_per_million_tokens": 4.50,
        },
    },
    "ocr": {
        "mistral-ocr-latest": {"per_thousand_pages": 4.00},
        "mistral-ocr-4-0": {"per_thousand_pages": 4.00},
    },
}


def build_provider_economics(
    observations: list[dict[str, Any]],
    *,
    parser_model: str,
    extractor_model: str,
) -> dict[str, Any]:
    events = [
        event
        for observation in observations
        for event in observation.get("provider_attempts", [])
        if isinstance(event, dict)
    ]
    successful = [event for event in events if event.get("status") == "succeeded"]
    usage = _aggregate_usage(successful)
    failures = Counter(
        str(event.get("error") or "unknown") for event in events if event.get("status") == "failed"
    )
    return {
        "usage": usage,
        "attempts": {
            "total": len(events),
            "succeeded": len(successful),
            "failed": len(events) - len(successful),
            "failure_codes": dict(sorted(failures.items())),
        },
        "cost": _cost_from_usage(
            usage,
            parser_model=parser_model,
            extractor_model=extractor_model,
        ),
        "pricing_snapshot": PRICING_SNAPSHOT,
    }


def _aggregate_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "ocr_pages_processed": 0,
        "ocr_document_size_bytes": 0,
        "extractor_input_tokens": 0,
        "extractor_cached_input_tokens": 0,
        "extractor_output_tokens": 0,
        "extractor_total_tokens": 0,
    }
    for event in events:
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        if event.get("stage") == "parser":
            totals["ocr_pages_processed"] += _integer(usage.get("pages_processed"))
            totals["ocr_document_size_bytes"] += _integer(usage.get("document_size_bytes"))
        elif event.get("stage") == "extractor":
            totals["extractor_input_tokens"] += _integer(usage.get("input_tokens"))
            totals["extractor_cached_input_tokens"] += _integer(usage.get("cached_input_tokens"))
            totals["extractor_output_tokens"] += _integer(usage.get("output_tokens"))
            totals["extractor_total_tokens"] += _integer(usage.get("total_tokens"))
    return totals


def _cost_from_usage(
    usage: dict[str, int],
    *,
    parser_model: str,
    extractor_model: str,
) -> dict[str, Any]:
    ocr_pricing = PRICING_SNAPSHOT["ocr"].get(parser_model)
    extractor_pricing = PRICING_SNAPSHOT["extractor"].get(extractor_model)
    if ocr_pricing is None or extractor_pricing is None:
        return {
            "status": "unavailable_unknown_pricing",
            "estimated_total_usd": None,
            "parser_model": parser_model,
            "extractor_model": extractor_model,
        }

    cached = min(
        usage["extractor_cached_input_tokens"],
        usage["extractor_input_tokens"],
    )
    uncached = usage["extractor_input_tokens"] - cached
    ocr_cost = usage["ocr_pages_processed"] * ocr_pricing["per_thousand_pages"] / 1000
    input_cost = uncached * extractor_pricing["input_per_million_tokens"] / 1_000_000
    cached_input_cost = cached * extractor_pricing["cached_input_per_million_tokens"] / 1_000_000
    output_cost = usage["extractor_output_tokens"] * (
        extractor_pricing["output_per_million_tokens"] / 1_000_000
    )
    total = ocr_cost + input_cost + cached_input_cost + output_cost
    return {
        "status": "estimated_from_provider_reported_usage",
        "parser_model": parser_model,
        "extractor_model": extractor_model,
        "ocr_usd": round(ocr_cost, 6),
        "extractor_input_usd": round(input_cost, 6),
        "extractor_cached_input_usd": round(cached_input_cost, 6),
        "extractor_output_usd": round(output_cost, 6),
        "estimated_total_usd": round(total, 6),
        "claim_boundary": (
            "List-price estimate from provider-reported usage; provider billing records remain "
            "the source of truth. Failed attempts without usage metadata may be billed but are "
            "not included."
        ),
    }


def _integer(value: Any) -> int:
    return int(value) if value is not None else 0
