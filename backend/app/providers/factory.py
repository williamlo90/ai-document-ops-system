from __future__ import annotations

from app.core.settings import Settings
from app.core.provider_egress import validate_provider_endpoint
from app.providers.contracts import ExtractorProvider, ParserProvider
from app.providers.llm_json import LlmJsonInvoiceExtractor
from app.providers.mistral import MistralOcrParserProvider
from app.providers.mock import MockInvoiceExtractor, MockParserProvider


def build_parser_provider(settings: Settings) -> ParserProvider:
    provider = settings.parser_provider.strip().lower()
    if provider == "mock":
        return MockParserProvider()
    if provider == "mistral_ocr":
        validate_provider_endpoint(
            settings.mistral_ocr_endpoint,
            settings.mistral_allowed_hosts,
            label="Mistral OCR",
        )
        return MistralOcrParserProvider(
            api_key=settings.mistral_api_key or "",
            endpoint=settings.mistral_ocr_endpoint,
            model=settings.mistral_ocr_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"Unsupported parser provider: {settings.parser_provider}")


def build_extractor_provider(settings: Settings) -> ExtractorProvider:
    provider = settings.extractor_provider.strip().lower()
    if provider == "mock":
        return MockInvoiceExtractor()
    if provider == "llm_json":
        validate_provider_endpoint(
            settings.extractor_endpoint,
            settings.extractor_allowed_hosts,
            label="invoice extractor",
        )
        return LlmJsonInvoiceExtractor(
            api_key=settings.extractor_api_key or "",
            endpoint=settings.extractor_endpoint,
            model=settings.extractor_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    raise ValueError(f"Unsupported extractor provider: {settings.extractor_provider}")
