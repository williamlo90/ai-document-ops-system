from __future__ import annotations

from app.core.settings import Settings
from app.providers.contracts import ExtractorProvider, ParserProvider
from app.providers.llm_json import LlmJsonInvoiceExtractor
from app.providers.mistral import MistralOcrParserProvider
from app.providers.mock import MockInvoiceExtractor, MockParserProvider


def build_parser_provider(settings: Settings) -> ParserProvider:
    provider = settings.parser_provider.strip().lower()
    if provider == "mock":
        return MockParserProvider()
    if provider == "mistral_ocr":
        return MistralOcrParserProvider(
            api_key=settings.mistral_api_key or "",
            endpoint=settings.mistral_ocr_endpoint,
            model=settings.mistral_ocr_model,
        )
    raise ValueError(f"Unsupported parser provider: {settings.parser_provider}")


def build_extractor_provider(settings: Settings) -> ExtractorProvider:
    provider = settings.extractor_provider.strip().lower()
    if provider == "mock":
        return MockInvoiceExtractor()
    if provider == "llm_json":
        return LlmJsonInvoiceExtractor(
            api_key=settings.extractor_api_key or "",
            endpoint=settings.extractor_endpoint,
            model=settings.extractor_model,
        )
    raise ValueError(f"Unsupported extractor provider: {settings.extractor_provider}")
