from __future__ import annotations

from typing import Any

PROVIDER_PRICING: dict[str, dict[str, float]] = {
    "mock": {
        "cost_per_document": 0.0,
        "cost_per_second": 0.0,
    },
    "mock_parser+mock_extractor": {
        "cost_per_document": 0.0,
        "cost_per_second": 0.0,
    },
    "mistral_ocr+llm_json": {
        "cost_per_document": 0.02,
        "cost_per_second": 0.002,
    },
}


def get_cost_estimate(
    provider_name: str,
    document_count: int,
    total_latency_ms: float,
) -> dict[str, Any]:
    pricing = PROVIDER_PRICING.get(provider_name)
    if pricing is None:
        return {
            "provider": provider_name,
            "document_count": document_count,
            "total_latency_ms": total_latency_ms,
            "estimated_cost_per_document": None,
            "estimated_cost_total": None,
            "note": "Unknown provider — no pricing configured",
        }
    per_document = pricing["cost_per_document"]
    per_second = pricing["cost_per_second"]
    latency_cost = per_second * (total_latency_ms / 1000.0)
    total_cost = (per_document * document_count) + latency_cost
    return {
        "provider": provider_name,
        "document_count": document_count,
        "total_latency_ms": total_latency_ms,
        "estimated_cost_per_document": (
            round(per_document + latency_cost / document_count, 6) if document_count else 0.0
        ),
        "estimated_cost_total": round(total_cost, 6),
    }
