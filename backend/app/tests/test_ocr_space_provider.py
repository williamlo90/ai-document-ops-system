import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from app.providers.ocr_space import OcrSpaceParserProvider
from app.providers.contracts import DocumentSource, ProviderError


class OcrSpaceTests(unittest.TestCase):
    def test_success_and_partial_failure(self):
        good = {
            "OCRExitCode": 1,
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"FileParseExitCode": 1, "ParsedText": "Invoice 123"}],
        }
        post = Mock(return_value=good)
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "a.pdf"
            p.write_bytes(b"%PDF-1.4 test")
            source = DocumentSource("a", p, "a.pdf", "application/pdf")
            parser = OcrSpaceParserProvider("secret", post_form=post)
            result = parser.parse(source)
            self.assertEqual(result.text, "Invoice 123")
            self.assertEqual(result.pages[0].page_number, 1)
            self.assertNotIn("secret", post.call_args.args[0])
            for data in [
                {},
                dict(good, OCRExitCode=2),
                dict(good, IsErroredOnProcessing=True),
                dict(good, ParsedResults=[]),
                dict(good, ParsedResults=[{"FileParseExitCode": -10, "ParsedText": "partial"}]),
                dict(good, ParsedResults=[{"FileParseExitCode": 1, "ParsedText": ""}]),
            ]:
                post.return_value = data
                with self.assertRaises(ProviderError):
                    parser.parse(source)
            p.write_bytes(b"%PDF-" + b"x" * 1_000_000)
            post.reset_mock()
            with self.assertRaises(ProviderError):
                parser.parse(source)
            post.assert_not_called()

    def test_missing_key(self):
        with self.assertRaises(ValueError):
            OcrSpaceParserProvider("")
