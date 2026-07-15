from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import Settings
from app.providers.contracts import ExtractorProvider, ParserProvider
from app.providers.llm_json import LlmJsonInvoiceExtractor
from app.providers.mistral import MistralOcrParserProvider
from app.providers.mock import MockInvoiceExtractor, MockParserProvider


@dataclass(frozen=True)
class BenchmarkProviderPair:
    key: str
    label: str
    parser_name: str
    extractor_name: str
    requires_credentials: bool = False


MOCK_PROVIDER_PAIR = BenchmarkProviderPair(
    key="mock",
    label="Mock parser + mock extractor",
    parser_name="mock_parser",
    extractor_name="mock_extractor",
)

MISTRAL_LLM_PROVIDER_PAIR = BenchmarkProviderPair(
    key="mistral_ocr+llm_json",
    label="Mistral OCR + LLM JSON extractor",
    parser_name="mistral_ocr",
    extractor_name="llm_json",
    requires_credentials=True,
)


def available_provider_pairs(settings: Settings) -> tuple[BenchmarkProviderPair, ...]:
    pairs = [MOCK_PROVIDER_PAIR]
    if _real_provider_configured(settings):
        pairs.append(MISTRAL_LLM_PROVIDER_PAIR)
    return tuple(pairs)


def build_provider_pair(
    key: str,
    settings: Settings,
) -> tuple[BenchmarkProviderPair, ParserProvider, ExtractorProvider]:
    normalized = key.strip().lower() or MOCK_PROVIDER_PAIR.key
    if normalized == MOCK_PROVIDER_PAIR.key:
        return MOCK_PROVIDER_PAIR, MockParserProvider(), MockInvoiceExtractor()
    if normalized == MISTRAL_LLM_PROVIDER_PAIR.key and _real_provider_configured(settings):
        return (
            MISTRAL_LLM_PROVIDER_PAIR,
            MistralOcrParserProvider(
                api_key=settings.mistral_api_key or "",
                endpoint=settings.mistral_ocr_endpoint,
                model=settings.mistral_ocr_model,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
            LlmJsonInvoiceExtractor(
                api_key=settings.extractor_api_key or "",
                endpoint=settings.extractor_endpoint,
                model=settings.extractor_model,
                timeout_seconds=settings.provider_timeout_seconds,
            ),
        )
    raise ValueError(f"Benchmark provider is not available: {key}")


def _real_provider_configured(settings: Settings) -> bool:
    return all(
        (
            settings.mistral_api_key,
            settings.mistral_ocr_endpoint,
            settings.mistral_ocr_model,
            settings.extractor_api_key,
            settings.extractor_endpoint,
            settings.extractor_model,
        )
    )
