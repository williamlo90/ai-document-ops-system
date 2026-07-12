from __future__ import annotations

from dataclasses import dataclass

from app.benchmark.models import EvaluationDataset
from app.benchmark.providers import BenchmarkProviderPair
from app.core.settings import Settings


class BenchmarkRunBlocked(ValueError):
    pass


@dataclass(frozen=True)
class BenchmarkSafetyInfo:
    provider_mode: str
    max_documents: int | None
    message: str


def provider_mode(provider: BenchmarkProviderPair) -> str:
    return "real" if provider.requires_credentials else "mock"


def safety_info(provider: BenchmarkProviderPair, settings: Settings) -> BenchmarkSafetyInfo:
    if provider.requires_credentials:
        max_documents = max(1, settings.benchmark_real_provider_max_documents)
        return BenchmarkSafetyInfo(
            provider_mode="real",
            max_documents=max_documents,
            message=f"Real provider mode can spend API credits. Limit: {max_documents} document(s) per run.",
        )
    return BenchmarkSafetyInfo(
        provider_mode="mock",
        max_documents=None,
        message="Mock mode does not call paid provider APIs.",
    )


def validate_benchmark_run(
    dataset: EvaluationDataset,
    provider: BenchmarkProviderPair,
    settings: Settings,
) -> None:
    if not provider.requires_credentials:
        return
    max_documents = max(1, settings.benchmark_real_provider_max_documents)
    documents_count = len(dataset.documents)
    if documents_count > max_documents:
        raise BenchmarkRunBlocked(
            "Real provider benchmark blocked: "
            f"dataset has {documents_count} document(s), limit is {max_documents}. "
            "Use a smaller dataset or increase BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS locally."
        )
