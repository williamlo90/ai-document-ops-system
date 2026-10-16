import tempfile
import unittest
from io import BytesIO
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import Mock
from app.providers.ocr_space import OcrSpaceParserProvider, OcrSpaceKeyPool, _positional_table_text
from app.providers.contracts import DocumentSource, ProviderError


class OcrSpaceTests(unittest.TestCase):
    def test_key_pool_fails_over_and_skips_primary_until_cooldown_expires(self):
        good = {
            "OCRExitCode": 1,
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"FileParseExitCode": 1, "ParsedText": "Invoice 123"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-test")
            source = DocumentSource("a", path, "a.pdf", "application/pdf")
            now = [100.0]
            seen = []

            def post(url, payload, headers):
                seen.append(headers["apikey"])
                if headers["apikey"] == "primary" and now[0] < 160:
                    raise HTTPError(url, 429, "quota", {}, BytesIO(b'{"retryAfter":60}'))
                return good

            pool = OcrSpaceKeyPool(
                ["primary", "backup", "backup"], post_form=post, clock=lambda: now[0]
            )
            self.assertEqual(pool.parse(source).text, "Invoice 123")
            self.assertEqual(seen, ["primary", "backup"])
            self.assertEqual(
                [r["http_status"] for r in pool.last_attempts if r["status"] == "failed"], [429]
            )
            pool.parse(source)
            self.assertEqual(seen, ["primary", "backup", "backup"])
            now[0] = 161
            pool.parse(source)
            self.assertEqual(seen[-1], "primary")
            self.assertNotIn("api_key=", repr(pool._providers[0]))

    def test_key_pool_retries_transport_with_another_key_and_stops_after_all_auth_failures(self):
        good = {
            "OCRExitCode": 1,
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"FileParseExitCode": 1, "ParsedText": "Invoice 123"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-test")
            source = DocumentSource("a", path, "a.pdf", "application/pdf")
            send = Mock(side_effect=[TimeoutError(), good])
            pool = OcrSpaceKeyPool(["first", "second"], post_form=send)
            self.assertEqual(pool.parse(source).text, "Invoice 123")
            self.assertEqual(send.call_count, 2)
            reject = Mock(
                side_effect=HTTPError("https://api.ocr.space", 403, "forbidden", {}, BytesIO(b"{}"))
            )
            pool = OcrSpaceKeyPool(["first", "second"], post_form=reject)
            for _ in range(2):
                with self.assertRaises(ProviderError) as caught:
                    pool.parse(source)
                self.assertFalse(caught.exception.retryable)
                self.assertEqual(caught.exception.http_status, 401)
            self.assertEqual(reject.call_count, 2)

    def test_key_pool_is_bounded_and_honors_shortest_remaining_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-test")
            source = DocumentSource("a", path, "a.pdf", "application/pdf")

            def post(url, payload, headers):
                delay = 60 if headers["apikey"] == "first" else 120
                raise HTTPError(
                    url, 429, "quota", {}, BytesIO(('{"retryAfter":%d}' % delay).encode())
                )

            send = Mock(side_effect=post)
            pool = OcrSpaceKeyPool(["first", "second"], post_form=send, clock=lambda: 10)
            for _ in range(2):
                with self.assertRaises(ProviderError) as caught:
                    pool.parse(source)
                self.assertEqual(caught.exception.retry_after_seconds, 60)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(pool.last_attempts, [])

    def test_key_pool_disables_rejected_keys_but_does_not_retry_bad_ocr_answers(self):
        good = {
            "OCRExitCode": 1,
            "IsErroredOnProcessing": False,
            "ParsedResults": [{"FileParseExitCode": 1, "ParsedText": "Invoice 123"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-test")
            source = DocumentSource("a", path, "a.pdf", "application/pdf")
            send = Mock(
                side_effect=[
                    {"IsErroredOnProcessing": True, "ErrorMessage": ["API key is invalid"]},
                    good,
                    good,
                ]
            )
            pool = OcrSpaceKeyPool(["first", "second"], post_form=send)
            pool.parse(source)
            pool.parse(source)
            self.assertEqual(
                [c.args[2]["apikey"] for c in send.call_args_list], ["first", "second", "second"]
            )
            invalid = Mock(return_value={"IsErroredOnProcessing": True, "OCRExitCode": 2})
            with self.assertRaises(ProviderError):
                OcrSpaceKeyPool(["first", "second"], post_form=invalid).parse(source)
            self.assertEqual(invalid.call_count, 1)

    def test_rate_limit_metadata_is_retained_without_response_body(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.pdf"
            path.write_bytes(b"%PDF-test")
            source = DocumentSource("a", path, "a.pdf", "application/pdf")
            for body, headers, expected in (
                (b'{"retryAfter":1766,"error":"private"}', {}, 1766),
                (b"{}", {"Retry-After": "50"}, 50),
                (b'{"retryAfter":-3}', {}, None),
            ):
                post = Mock(
                    side_effect=HTTPError(
                        "https://api.ocr.space", 429, "quota", headers, BytesIO(body)
                    )
                )
                with self.assertRaises(ProviderError) as caught:
                    OcrSpaceParserProvider("secret", post_form=post).parse(source)
                self.assertEqual(caught.exception.http_status, 429)
                self.assertEqual(caught.exception.retry_after_seconds, expected)
                self.assertTrue(caught.exception.retryable)
                self.assertNotIn("private", str(caught.exception))

    def test_missing_quantity_keeps_its_empty_column(self):
        def cell(text, x, y):
            return {
                "LineText": text,
                "Words": [{"WordText": text, "Left": x, "Top": y, "Height": 10}],
            }

        overlay = {
            "Lines": [
                cell(name, x, 100)
                for name, x in (
                    ("ITEM", 10),
                    ("UNIT", 100),
                    ("QUANTITY", 150),
                    ("UNIT PRICE", 200),
                    ("LINE TOTAL", 250),
                )
            ]
            + [
                cell("Part A", 10, 130),
                cell("EA", 100, 130),
                cell("55.00", 200, 130),
                cell("165.00", 250, 130),
                cell("Subtotal", 200, 160),
            ]
        }
        original = "INVOICE\nITEM\tUNIT\tQUANTITY\tUNIT PRICE\tLINE TOTAL\nPart A\tEA\t55.00\t165.00\nSubtotal\t165.00"
        result = _positional_table_text(original, overlay)
        self.assertIn("| Part A | EA |  | 55.00 | 165.00 |", result)
        self.assertIn("Subtotal\t165.00", result)
        self.assertEqual(_positional_table_text(original, {}), original)

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
