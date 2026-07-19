from __future__ import annotations

import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from app.core.provider_egress import (
    validate_configured_provider_egress,
    validate_provider_endpoint,
)
from app.core.settings import Settings
from app.providers.contracts import ProviderError
from app.providers.http_transport import RejectRedirects, post_json_without_redirects


class ProviderEndpointPolicyTests(unittest.TestCase):
    def test_accepts_exact_allowlisted_https_host(self) -> None:
        validate_provider_endpoint(
            "https://api.groq.com/openai/v1/chat/completions",
            ("api.groq.com",),
            label="invoice extractor",
        )

    def test_rejects_insecure_or_confusing_provider_urls(self) -> None:
        cases = (
            "http://api.groq.com/openai/v1/chat/completions",
            "https://api.groq.com.evil.test/openai/v1/chat/completions",
            "https://api.groq.com:8443/openai/v1/chat/completions",
            "https://user:pass@api.groq.com/openai/v1/chat/completions",
            "https://api.groq.com/openai/v1/chat/completions?token=secret",
            "https://api.groq.com/openai/v1/chat/completions#fragment",
        )
        for endpoint in cases:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_provider_endpoint(
                    endpoint,
                    ("api.groq.com",),
                    label="invoice extractor",
                )

    def test_configured_real_provider_is_validated_at_startup_boundary(self) -> None:
        settings = Settings(
            app_env="local",
            admin_token="test-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1_000,
            parser_provider="mistral_ocr",
            mistral_api_key="secret",
            mistral_ocr_endpoint="https://attacker.test/ocr",
        )
        with self.assertRaises(ValueError):
            validate_configured_provider_egress(settings)


class ProviderHttpTransportTests(unittest.TestCase):
    def test_transport_installs_redirect_rejection_and_does_not_retry_redirect(self) -> None:
        with patch("app.providers.http_transport.urllib.request.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = urllib.error.HTTPError(
                url="https://api.groq.com/start",
                code=302,
                msg="redirect",
                hdrs={"Location": "https://attacker.test/collect"},
                fp=None,
            )
            with self.assertRaises(ProviderError) as caught:
                post_json_without_redirects(
                    "https://api.groq.com/start",
                    {"document": "private"},
                    {"Authorization": "Bearer secret"},
                    timeout_seconds=10,
                    provider_name="llm_json",
                    http_error_code="extractor_http_error",
                )

        self.assertFalse(caught.exception.retryable)
        handler = build_opener.call_args.args[0]
        self.assertIsInstance(handler, RejectRedirects)
        self.assertEqual(build_opener.return_value.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
