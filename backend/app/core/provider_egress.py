from __future__ import annotations

from urllib.parse import urlsplit

from app.core.settings import Settings


def validate_configured_provider_egress(settings: Settings) -> None:
    parser = settings.parser_provider.strip().lower()
    extractor = settings.extractor_provider.strip().lower()
    if parser == "mistral_ocr":
        validate_provider_endpoint(
            settings.mistral_ocr_endpoint,
            settings.mistral_allowed_hosts,
            label="Mistral OCR",
        )
    if extractor == "llm_json":
        validate_provider_endpoint(
            settings.extractor_endpoint,
            settings.extractor_allowed_hosts,
            label="invoice extractor",
        )


def validate_provider_endpoint(
    endpoint: str,
    allowed_hosts: tuple[str, ...],
    *,
    label: str,
) -> None:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} endpoint is invalid") from exc
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    normalized_hosts = {
        host.strip().rstrip(".").casefold() for host in allowed_hosts if host.strip()
    }
    if parsed.scheme.casefold() != "https":
        raise ValueError(f"{label} endpoint must use HTTPS")
    if not hostname or hostname not in normalized_hosts:
        raise ValueError(f"{label} endpoint host is not allowlisted")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} endpoint must not contain credentials")
    if port not in {None, 443}:
        raise ValueError(f"{label} endpoint must use the default HTTPS port")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} endpoint must not contain a query or fragment")
