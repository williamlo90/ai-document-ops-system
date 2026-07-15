from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app.core.settings import Settings
from app.providers.contracts import DocumentSource, ParsedDocument, ProviderError
from app.providers.factory import build_extractor_provider, build_parser_provider
from app.providers.llm_json import LlmJsonInvoiceExtractor, _post_json as llm_post_json
from app.providers.mistral import MistralOcrParserProvider, _post_json as mistral_post_json


class ProviderFactoryTests(unittest.TestCase):
    def settings(self, **overrides) -> Settings:
        values = {
            "app_env": "test",
            "admin_token": "test-token",
            "upload_root": Path("uploads"),
            "max_upload_bytes": 1000,
            "parser_provider": "mock",
            "extractor_provider": "mock",
            "mistral_api_key": None,
            "mistral_ocr_endpoint": "https://example.test/ocr",
            "mistral_ocr_model": "mistral-ocr-latest",
            "extractor_api_key": None,
            "extractor_endpoint": "",
            "extractor_model": "",
        }
        values.update(overrides)
        return Settings(**values)

    def test_defaults_build_mock_providers(self) -> None:
        parser = build_parser_provider(self.settings())
        extractor = build_extractor_provider(self.settings())

        self.assertEqual(parser.provider_name, "mock_parser")
        self.assertEqual(extractor.provider_name, "mock_extractor")

    def test_mistral_parser_requires_api_key(self) -> None:
        with self.assertRaises(ValueError):
            build_parser_provider(self.settings(parser_provider="mistral_ocr"))

    def test_llm_json_extractor_requires_config(self) -> None:
        with self.assertRaises(ValueError):
            build_extractor_provider(self.settings(extractor_provider="llm_json"))

        extractor = build_extractor_provider(
            self.settings(
                extractor_provider="llm_json",
                extractor_api_key="secret",
                extractor_endpoint="https://example.test/extract",
                extractor_model="invoice-model",
            )
        )

        self.assertEqual(extractor.provider_name, "llm_json")

    def test_configured_timeout_reaches_real_providers(self) -> None:
        settings = self.settings(
            parser_provider="mistral_ocr",
            extractor_provider="llm_json",
            mistral_api_key="secret",
            extractor_api_key="secret",
            extractor_endpoint="https://example.test/extract",
            extractor_model="invoice-model",
            provider_timeout_seconds=17,
        )

        parser = build_parser_provider(settings)
        extractor = build_extractor_provider(settings)

        self.assertEqual(parser.timeout_seconds, 17)
        self.assertEqual(extractor.timeout_seconds, 17)

    def test_unknown_provider_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            build_parser_provider(self.settings(parser_provider="unknown"))
        with self.assertRaises(ValueError):
            build_extractor_provider(self.settings(extractor_provider="unknown"))


class MistralOcrParserProviderTests(unittest.TestCase):
    def test_posts_pdf_data_url_and_normalizes_pages(self) -> None:
        captured = {}

        def fake_post_json(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            return {
                "id": "trace-123",
                "pages": [
                    {"index": 0, "markdown": "Invoice #INV-001"},
                    {"index": 1, "text": "Total 110.00"},
                ],
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invoice.pdf"
            path.write_bytes(b"%PDF- invoice")
            provider = MistralOcrParserProvider(
                api_key="secret",
                endpoint="https://example.test/ocr",
                model="mistral-ocr-latest",
                post_json=fake_post_json,
            )
            parsed = provider.parse(
                DocumentSource(
                    storage_key="private-key",
                    path=path,
                    original_filename="invoice.pdf",
                    content_type="application/pdf",
                )
            )

        self.assertEqual(captured["url"], "https://example.test/ocr")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["payload"]["model"], "mistral-ocr-latest")
        self.assertTrue(
            captured["payload"]["document"]["document_url"].startswith(
                "data:application/pdf;base64,"
            )
        )
        self.assertEqual(parsed.provider_name, "mistral_ocr")
        self.assertEqual(parsed.provider_trace_id, "trace-123")
        self.assertEqual(len(parsed.pages), 2)
        self.assertIn("Invoice #INV-001", parsed.text)
        self.assertIn("Total 110.00", parsed.text)

    def test_http_4xx_error_is_not_retryable(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="https://example.test/ocr",
                code=400,
                msg="bad request",
                hdrs=None,
                fp=None,
            ),
        ):
            with self.assertRaises(ProviderError) as caught:
                mistral_post_json("https://example.test/ocr", {"model": "x"}, {})

        self.assertEqual(str(caught.exception), "ocr_http_error")
        self.assertFalse(caught.exception.retryable)

    def test_http_5xx_error_is_retryable(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="https://example.test/ocr",
                code=502,
                msg="bad gateway",
                hdrs=None,
                fp=None,
            ),
        ):
            with self.assertRaises(ProviderError) as caught:
                mistral_post_json("https://example.test/ocr", {"model": "x"}, {})

        self.assertEqual(str(caught.exception), "ocr_http_error")
        self.assertTrue(caught.exception.retryable)

    def test_http_client_uses_configured_timeout(self) -> None:
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"pages": []}'

            mistral_post_json(
                "https://example.test/ocr",
                {"model": "x"},
                {},
                timeout_seconds=17,
            )

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 17)


class LlmJsonInvoiceExtractorTests(unittest.TestCase):
    def test_posts_ocr_text_and_maps_invoice_data(self) -> None:
        captured = {}

        def fake_post_json(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            return {
                "data": {
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "INV-001",
                    "invoice_date": "2026-06-18",
                    "due_date": "2026-07-18",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "110.00",
                    "currency": "USD",
                    "line_items": [
                        {
                            "description": "Freight",
                            "quantity": "1",
                            "unit_price": "100.00",
                            "amount": "100.00",
                        }
                    ],
                    "field_confidence": [
                        {"field_name": "total", "score": "0.98", "source_page": 1}
                    ],
                }
            }

        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=fake_post_json,
        )
        result = extractor.extract_invoice(
            ParsedDocument(
                text=(
                    "FROM\nAcme Logistics\n100 Example Street\n"
                    "Invoice #INV-001 total 110.00"
                ),
                provider_trace_id="trace-123",
            )
        )

        self.assertEqual(captured["url"], "https://example.test/extract")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(captured["payload"]["model"], "invoice-model")
        self.assertEqual(
            captured["payload"]["messages"][1]["content"],
            "FROM\nAcme Logistics\n100 Example Street\nInvoice #INV-001 total 110.00",
        )
        system_prompt = captured["payload"]["messages"][0]["content"]
        self.assertIn("Never infer or guess", system_prompt)
        self.assertIn("return null rather than zero", system_prompt)
        self.assertEqual(result.provider_name, "llm_json")
        self.assertEqual(result.provider_trace_id, "trace-123")
        self.assertEqual(result.extraction.data.vendor_name, "Acme Logistics")
        self.assertEqual(result.extraction.data.invoice_number, "INV-001")
        self.assertEqual(str(result.extraction.data.total), "110.00")
        self.assertEqual(len(result.extraction.data.line_items), 1)
        self.assertEqual(len(result.extraction.confidence), 1)

    def test_accepts_chat_completion_json_content(self) -> None:
        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=lambda _url, _payload, _headers: {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"vendor_name":"Acme","invoice_number":"INV-002",'
                                '"invoice_date":"2026-06-18","total":"25.00","currency":"USD"}'
                            )
                        }
                    }
                ]
            },
        )

        result = extractor.extract_invoice(ParsedDocument(text="invoice"))

        self.assertEqual(result.extraction.data.invoice_number, "INV-002")
        self.assertEqual(str(result.extraction.data.total), "25.00")

    def test_invalid_json_mapping_raises_provider_error(self) -> None:
        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=lambda _url, _payload, _headers: {"data": {"invoice_date": "18/06/2026"}},
        )

        with self.assertRaises(ProviderError) as caught:
            extractor.extract_invoice(ParsedDocument(text="invoice"))

        self.assertEqual(str(caught.exception), "invalid_extractor_response")

    def test_empty_invoice_payload_raises_provider_error(self) -> None:
        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=lambda _url, _payload, _headers: {
                "choices": [{"message": {"content": "{}"}}]
            },
        )

        with self.assertRaises(ProviderError) as caught:
            extractor.extract_invoice(ParsedDocument(text="invoice"))

        self.assertEqual(str(caught.exception), "invalid_extractor_response")

    def test_vendor_without_seller_or_business_context_is_removed(self) -> None:
        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=lambda _url, _payload, _headers: {
                "data": {
                    "vendor_name": "Northstar Accounts Demo",
                    "invoice_number": "MV-1007",
                    "invoice_date": "2026-07-07",
                    "total": "99.00",
                    "currency": "USD",
                }
            },
        )

        result = extractor.extract_invoice(
            ParsedDocument(
                text=(
                    "INVOICE\nNorthstar Accounts Demo\nSynthetic fixture\n"
                    "Invoice number MV-1007\nTotal 99.00"
                )
            )
        )

        self.assertIsNone(result.extraction.data.vendor_name)

    def test_vendor_with_business_address_is_preserved_without_from_label(self) -> None:
        extractor = LlmJsonInvoiceExtractor(
            api_key="secret",
            endpoint="https://example.test/extract",
            model="invoice-model",
            post_json=lambda _url, _payload, _headers: {
                "data": {
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "AC-1001",
                    "invoice_date": "2026-07-01",
                    "total": "110.00",
                    "currency": "USD",
                }
            },
        )

        result = extractor.extract_invoice(
            ParsedDocument(text="Acme Logistics\n100 Example Street\nInvoice AC-1001")
        )

        self.assertEqual(result.extraction.data.vendor_name, "Acme Logistics")

    def test_http_4xx_error_is_not_retryable(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="https://example.test/extract",
                code=401,
                msg="unauthorized",
                hdrs=None,
                fp=None,
            ),
        ):
            with self.assertRaises(ProviderError) as caught:
                llm_post_json("https://example.test/extract", {"model": "x"}, {})

        self.assertEqual(str(caught.exception), "extractor_http_error")
        self.assertFalse(caught.exception.retryable)

    def test_http_5xx_error_is_retryable(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                url="https://example.test/extract",
                code=500,
                msg="server error",
                hdrs=None,
                fp=None,
            ),
        ):
            with self.assertRaises(ProviderError) as caught:
                llm_post_json("https://example.test/extract", {"model": "x"}, {})

        self.assertEqual(str(caught.exception), "extractor_http_error")
        self.assertTrue(caught.exception.retryable)

    def test_http_client_uses_configured_timeout(self) -> None:
        with patch("urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b"{}"

            llm_post_json(
                "https://example.test/extract",
                {"model": "x"},
                {},
                timeout_seconds=17,
            )

        self.assertEqual(urlopen.call_args.kwargs["timeout"], 17)


if __name__ == "__main__":
    unittest.main()
