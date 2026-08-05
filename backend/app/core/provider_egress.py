from __future__ import annotations

from urllib.parse import urlsplit


class ProviderEgressRejected(ValueError):
    pass


def validate_provider_endpoint(endpoint: str, allowed_hosts: frozenset[str]) -> str:
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderEgressRejected("Provider endpoint must use HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProviderEgressRejected("Provider endpoint cannot contain credentials, query, or fragment")
    if parsed.hostname not in allowed_hosts:
        raise ProviderEgressRejected("Provider host is not allowlisted")
    return endpoint
