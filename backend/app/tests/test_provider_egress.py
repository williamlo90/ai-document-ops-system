import unittest

from app.core.provider_egress import ProviderEgressRejected, validate_provider_endpoint
from app.providers.http_transport import ProviderHttpTransport


class ProviderEgressTests(unittest.TestCase):
    def test_https_exact_host_and_redirect_policy(self) -> None:
        allowed = frozenset({"api.example.com"})
        self.assertEqual(validate_provider_endpoint("https://api.example.com/v1", allowed), "https://api.example.com/v1")
        for endpoint in ("http://api.example.com", "https://user@api.example.com", "https://evil.example.com", "https://api.example.com?key=x"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ProviderEgressRejected):
                validate_provider_endpoint(endpoint, allowed)
        with self.assertRaises(ValueError):
            ProviderHttpTransport("https://api.example.com", allowed, follow_redirects=True).validated_endpoint()
