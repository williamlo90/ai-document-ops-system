import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.core.settings import Settings
from app.providers.contracts import DocumentSource, ProviderError
from app.providers.factory import build_parser_provider
from app.providers.gemini import GeminiOcrParserProvider


class GeminiTests(unittest.TestCase):
    def test_transcription_and_usage(self):
        response = {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "pages": [
                                            {"page_number": 1, "text": "Invoice 123"},
                                            {"page_number": 2, "text": "Total 20"},
                                        ]
                                    }
                                )
                            }
                        ]
                    },
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 200,
                "candidatesTokenCount": 20,
                "thoughtsTokenCount": 3,
                "totalTokenCount": 223,
            },
            "modelVersion": "resolved-model",
        }
        post = Mock(return_value=response)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.pdf"
            p.write_bytes(b"%PDF-1.4 synthetic")
            source = DocumentSource("test", p, p.name, "application/pdf")
            parser = GeminiOcrParserProvider("secret", post_json=post)
            result = parser.parse(source)
            self.assertEqual(result.pages[1].page_number, 2)
            self.assertEqual(result.usage.output_tokens, 23)
            self.assertEqual(result.provider_model, "resolved-model")
            url, payload, headers = post.call_args.args
            self.assertNotIn("secret", url)
            self.assertEqual(headers["x-goog-api-key"], "secret")
            self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 8192)
            for bad in [
                {},
                {"candidates": []},
                {"candidates": [{"finishReason": "MAX_TOKENS"}]},
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [{"text": '{"pages":[{"page_number":2,"text":"x"}]}'}]
                            },
                        }
                    ]
                },
            ]:
                post.return_value = bad
                with self.assertRaises(ProviderError):
                    parser.parse(source)
            post.reset_mock()
            p.write_bytes(b"not pdf")
            with self.assertRaises(ProviderError):
                parser.parse(source)
            post.assert_not_called()

    def test_factory_and_model_boundary(self):
        s = Settings(
            "test",
            None,
            Path("uploads"),
            1000,
            parser_provider="gemini_ocr",
            gemini_api_key="secret",
        )
        self.assertIsInstance(build_parser_provider(s), GeminiOcrParserProvider)
        with self.assertRaises(ValueError):
            GeminiOcrParserProvider("")
        with self.assertRaises(ValueError):
            GeminiOcrParserProvider("secret", model="../evil?key=abc")
