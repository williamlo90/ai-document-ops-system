from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import Settings, load_settings  # noqa: E402


def main() -> None:
    settings = load_settings()
    base_url = _validated_base_url(settings)

    if not settings.erpnext_api_key or not settings.erpnext_api_secret:
        raise SystemExit("ERPNEXT_API_KEY and ERPNEXT_API_SECRET must be set in .env.")

    ping = _get_json(
        f"{base_url}/api/method/ping",
        timeout=settings.erpnext_timeout_seconds,
    )
    if ping.get("message") != "pong":
        raise SystemExit("ERPNext health check returned an unexpected response.")

    identity = _get_json(
        f"{base_url}/api/method/frappe.auth.get_logged_user",
        timeout=settings.erpnext_timeout_seconds,
        authorization=f"token {settings.erpnext_api_key}:{settings.erpnext_api_secret}",
    ).get("message")
    if not identity:
        raise SystemExit("ERPNext authenticated check did not return a user.")
    if settings.erpnext_api_user and identity != settings.erpnext_api_user:
        raise SystemExit("ERPNext authenticated check returned an unexpected user.")

    print(f"ERPNext health: passed ({base_url})")
    print(f"ERPNext authentication: passed ({identity})")


def _validated_base_url(settings: Settings) -> str:
    base_url = settings.erpnext_base_url.rstrip("/")
    parsed = urlsplit(base_url)
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = {host.lower() for host in settings.erpnext_allowed_hosts}

    if parsed.username or parsed.password:
        raise SystemExit("ERPNEXT_BASE_URL must not contain credentials.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise SystemExit("ERPNEXT_BASE_URL must contain only scheme, host, and optional port.")
    if hostname not in allowed_hosts:
        raise SystemExit("ERPNEXT_BASE_URL host is not listed in ERPNEXT_ALLOWED_HOSTS.")
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit("ERPNEXT_BASE_URL must use HTTP or HTTPS.")
    if parsed.scheme == "http" and hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Plain HTTP is allowed only for a loopback ERPNext sandbox.")
    return base_url


def _get_json(url: str, *, timeout: int, authorization: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if authorization:
        headers["Authorization"] = authorization
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ERPNext smoke test failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("ERPNext returned a non-object JSON response.")
    return payload


if __name__ == "__main__":
    main()
