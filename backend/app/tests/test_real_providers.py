from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.core.settings import Settings
from app.providers.contracts import DocumentSource
from app.providers.factory import build_extractor_provider, build_parser_provider


MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY") or ""
EXTRACTOR_KEY = os.environ.get("EXTRACTOR_API_KEY") or ""
EXTRACTOR_ENDPOINT = os.environ.get("EXTRACTOR_ENDPOINT") or ""
HAVE_REAL_OCR = bool(MISTRAL_KEY)
HAVE_REAL_LLM = bool(EXTRACTOR_KEY and EXTRACTOR_ENDPOINT)


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "admin_token": "test-token",
        "upload_root": Path("uploads"),
        "max_upload_bytes": 10000000,
        "parser_provider": "mock",
        "extractor_provider": "mock",
        "mistral_api_key": MISTRAL_KEY or None,
        "mistral_ocr_endpoint": "https://api.mistral.ai/v1/ocr",
        "mistral_ocr_model": "mistral-ocr-latest",
        "extractor_api_key": EXTRACTOR_KEY or None,
        "extractor_endpoint": EXTRACTOR_ENDPOINT,
        "extractor_model": os.environ.get("EXTRACTOR_MODEL", ""),
    }
    values.update(overrides)
    return Settings(**values)


def _fake_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"


@unittest.skipIf(not HAVE_REAL_OCR, "MISTRAL_API_KEY not set")
class RealMistralOcrTests(unittest.TestCase):
    def test_parse_real_pdf(self) -> None:
        parser = build_parser_provider(_settings(parser_provider="mistral_ocr"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invoice.pdf"
            path.write_bytes(_fake_pdf_bytes())
            source = DocumentSource(
                storage_key="test-key",
                path=path,
                original_filename="invoice.pdf",
                content_type="application/pdf",
            )
            parsed = parser.parse(source)
        self.assertEqual(parsed.provider_name, "mistral_ocr")
        self.assertIsInstance(parsed.text, str)
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
