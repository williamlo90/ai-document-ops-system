from __future__ import annotations

from dataclasses import dataclass

from app.core.provider_egress import validate_provider_endpoint


@dataclass(frozen=True, slots=True)
class ProviderHttpTransport:
    endpoint: str
    allowed_hosts: frozenset[str]
    follow_redirects: bool = False

    def validated_endpoint(self) -> str:
        if self.follow_redirects:
            raise ValueError("Provider redirects must remain disabled")
        return validate_provider_endpoint(self.endpoint, self.allowed_hosts)
