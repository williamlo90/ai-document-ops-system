from __future__ import annotations

import unittest
from pathlib import Path

from app.core.settings import Settings, load_settings
from app.providers.contracts import DocumentSource
from app.providers.factory import build_extractor_provider, build_parser_provider


CONFIGURED_SETTINGS = load_settings()
MISTRAL_KEY = CONFIGURED_SETTINGS.mistral_api_key or ""
EXTRACTOR_KEY = CONFIGURED_SETTINGS.extractor_api_key or ""
EXTRACTOR_ENDPOINT = CONFIGURED_SETTINGS.extractor_endpoint
HAVE_REAL_OCR = bool(MISTRAL_KEY)
HAVE_REAL_LLM = bool(EXTRACTOR_KEY and EXTRACTOR_ENDPOINT)
SAMPLE_INVOICE = Path(__file__).resolve().parents[3] / "sample_invoice.pdf"


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "admin_token": "test-token",
        "upload_root": Path("uploads"),
        "max_upload_bytes": 10000000,
        "parser_provider": "mock",
        "extractor_provider": "mock",
        "mistral_api_key": MISTRAL_KEY or None,
        "mistral_ocr_endpoint": CONFIGURED_SETTINGS.mistral_ocr_endpoint,
        "mistral_ocr_model": CONFIGURED_SETTINGS.mistral_ocr_model,
        "extractor_api_key": EXTRACTOR_KEY or None,
        "extractor_endpoint": EXTRACTOR_ENDPOINT,
        "extractor_model": CONFIGURED_SETTINGS.extractor_model,
        "provider_timeout_seconds": CONFIGURED_SETTINGS.provider_timeout_seconds,
    }
    values.update(overrides)
    return Settings(**values)


@unittest.skipIf(not HAVE_REAL_OCR, "MISTRAL_API_KEY not set")
class RealMistralOcrTests(unittest.TestCase):
    def test_parse_real_pdf(self) -> None:
        parser = build_parser_provider(_settings(parser_provider="mistral_ocr"))
        source = DocumentSource(
            storage_key="test-key",
            path=SAMPLE_INVOICE,
            original_filename=SAMPLE_INVOICE.name,
            content_type="application/pdf",
        )
        parsed = parser.parse(source)
        self.assertEqual(parsed.provider_name, "mistral_ocr")
        self.assertTrue(parsed.text.strip())
        self.assertGreater(len(parsed.pages), 0)


@unittest.skipIf(not HAVE_REAL_LLM, "EXTRACTOR_API_KEY or EXTRACTOR_ENDPOINT not set")
class RealLlmJsonExtractorTests(unittest.TestCase):
    def test_extract_from_text(self) -> None:
        extractor = build_extractor_provider(
            _settings(
                extractor_provider="llm_json",
                extractor_api_key=EXTRACTOR_KEY,
                extractor_endpoint=EXTRACTOR_ENDPOINT,
            )
        )
        from app.providers.contracts import ParsedDocument

        result = extractor.extract_invoice(
            ParsedDocument(text="Invoice INV-001 from Acme Corp total 110.00 USD")
        )
        self.assertEqual(result.provider_name, "llm_json")
        self.assertIsNotNone(result.extraction.data.invoice_number)


if __name__ == "__main__":
    unittest.main()
