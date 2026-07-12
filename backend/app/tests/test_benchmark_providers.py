from __future__ import annotations

import unittest
from pathlib import Path

from app.benchmark.providers import available_provider_pairs, build_provider_pair
from app.core.settings import Settings
from app.providers.llm_json import LlmJsonInvoiceExtractor
from app.providers.mistral import MistralOcrParserProvider
from app.providers.mock import MockInvoiceExtractor, MockParserProvider


class BenchmarkProviderCatalogTests(unittest.TestCase):
    def test_mock_provider_is_always_available(self) -> None:
        pairs = available_provider_pairs(_settings())

        self.assertEqual([pair.key for pair in pairs], ["mock"])

    def test_real_provider_pair_is_available_only_when_configured(self) -> None:
        pairs = available_provider_pairs(
            _settings(
                mistral_api_key="mistral-key",
                extractor_api_key="extractor-key",
                extractor_endpoint="https://extractor.test",
                extractor_model="invoice-model",
            )
        )

        self.assertEqual([pair.key for pair in pairs], ["mock", "mistral_ocr+llm_json"])

    def test_build_mock_pair(self) -> None:
        pair, parser, extractor = build_provider_pair("mock", _settings())

        self.assertEqual(pair.key, "mock")
        self.assertIsInstance(parser, MockParserProvider)
        self.assertIsInstance(extractor, MockInvoiceExtractor)

    def test_build_real_pair_when_configured(self) -> None:
        pair, parser, extractor = build_provider_pair(
            "mistral_ocr+llm_json",
            _settings(
                mistral_api_key="mistral-key",
                extractor_api_key="extractor-key",
                extractor_endpoint="https://extractor.test",
                extractor_model="invoice-model",
            ),
        )

        self.assertEqual(pair.key, "mistral_ocr+llm_json")
        self.assertIsInstance(parser, MistralOcrParserProvider)
        self.assertIsInstance(extractor, LlmJsonInvoiceExtractor)

    def test_unconfigured_real_pair_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not available"):
            build_provider_pair("mistral_ocr+llm_json", _settings())

    def test_unknown_provider_pair_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not available"):
            build_provider_pair("unknown", _settings())


def _settings(
    *,
    mistral_api_key: str | None = None,
    extractor_api_key: str | None = None,
    extractor_endpoint: str = "",
    extractor_model: str = "",
) -> Settings:
    return Settings(
        app_env="local",
        admin_token="local-token",
        upload_root=Path("backend/data/uploads"),
        max_upload_bytes=1024,
        parser_provider="mock",
        extractor_provider="mock",
        mistral_api_key=mistral_api_key,
        mistral_ocr_endpoint="https://mistral.test",
        mistral_ocr_model="mistral-ocr-test",
        extractor_api_key=extractor_api_key,
        extractor_endpoint=extractor_endpoint,
        extractor_model=extractor_model,
    )


if __name__ == "__main__":
    unittest.main()
