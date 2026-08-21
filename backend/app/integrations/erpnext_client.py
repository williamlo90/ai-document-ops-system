from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import SplitResult, quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.integrations.models import IntegrationDeliveryError


class RejectERPNextRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class ERPNextClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str,
        api_secret: str,
        timeout_seconds: int,
        allowed_hosts: tuple[str, ...],
    ) -> None:
        self.base_url = validate_erpnext_base_url(base_url, allowed_hosts)
        self.timeout_seconds = timeout_seconds
        self._authorization = f"token {api_key}:{api_secret}"
        self._opener = build_opener(RejectERPNextRedirects())

    def create_purchase_invoice(self, values: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/resource/Purchase%20Invoice",
            payload=values,
            write_request=True,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise IntegrationDeliveryError(
                "ERPNext returned an invalid draft receipt",
                code="erpnext_invalid_receipt",
                retryable=False,
                outcome_unknown=True,
            )
        return data

    def find_purchase_invoices_by_delivery_key(self, delivery_key: str) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "filters": json.dumps(
                    {"custom_invoice_review_delivery_key": delivery_key},
                    separators=(",", ":"),
                ),
                "fields": json.dumps(
                    [
                        "name",
                        "docstatus",
                        "custom_invoice_review_payload_hash",
                    ],
                    separators=(",", ":"),
                ),
                "limit_page_length": "2",
            }
        )
        response = self._request(
            "GET",
            f"/api/resource/Purchase%20Invoice?{query}",
            write_request=False,
        )
        data = response.get("data")
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise IntegrationDeliveryError(
                "ERPNext returned an invalid lookup response",
                code="erpnext_invalid_lookup",
                retryable=True,
            )
        return data

    def get_purchase_invoice(self, name: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/api/resource/Purchase%20Invoice/{quote(name, safe='')}",
            write_request=False,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise IntegrationDeliveryError(
                "ERPNext returned an invalid draft document",
                code="erpnext_invalid_document",
                retryable=True,
            )
        return data

    def document_url(self, name: str) -> str:
        return f"{self.base_url}/app/purchase-invoice/{quote(name, safe='')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        write_request: bool,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization,
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _http_error(exc, write_request=write_request) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise IntegrationDeliveryError(
                "ERPNext could not confirm the request",
                code="erpnext_transport_error",
                retryable=not write_request,
                outcome_unknown=write_request,
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrationDeliveryError(
                "ERPNext returned an unreadable response",
                code="erpnext_invalid_json",
                retryable=not write_request,
                outcome_unknown=write_request,
            ) from exc
        if not isinstance(parsed, dict):
            raise IntegrationDeliveryError(
                "ERPNext returned an invalid response",
                code="erpnext_invalid_response",
                retryable=not write_request,
                outcome_unknown=write_request,
            )
        return parsed


def validate_erpnext_base_url(base_url: str, allowed_hosts: tuple[str, ...]) -> str:
    normalized = base_url.rstrip("/")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("ERPNext base URL is invalid") from exc
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    allowlist = {host.strip().rstrip(".").casefold() for host in allowed_hosts if host.strip()}
    _validate_erpnext_origin(parsed.scheme, hostname, port, allowlist)
    _validate_erpnext_url_shape(parsed)
    return normalized


def _validate_erpnext_origin(
    scheme: str,
    hostname: str,
    port: int | None,
    allowlist: set[str],
) -> None:
    if hostname not in allowlist:
        raise ValueError("ERPNext base URL host is not allowlisted")
    if scheme not in {"http", "https"}:
        raise ValueError("ERPNext base URL must use HTTP or HTTPS")
    if scheme == "http" and hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Plain HTTP is allowed only for a loopback ERPNext sandbox")
    if scheme == "https" and port not in {None, 443}:
        raise ValueError("ERPNext HTTPS must use the default port")


def _validate_erpnext_url_shape(parsed: SplitResult) -> None:
    if parsed.username or parsed.password:
        raise ValueError("ERPNext base URL must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("ERPNext base URL must contain only scheme, host, and optional port")


def _http_error(exc: HTTPError, *, write_request: bool) -> IntegrationDeliveryError:
    detail = _safe_error_detail(exc)
    if exc.code in {401, 403}:
        return IntegrationDeliveryError(
            "ERPNext authentication or permission was rejected",
            code="erpnext_access_denied",
            retryable=False,
        )
    if exc.code == 429:
        return IntegrationDeliveryError(
            "ERPNext is temporarily busy",
            code="erpnext_rate_limited",
            retryable=True,
        )
    if exc.code >= 500:
        return IntegrationDeliveryError(
            "ERPNext could not confirm the request",
            code="erpnext_server_error",
            retryable=not write_request,
            outcome_unknown=write_request,
        )
    duplicate = "duplicate" in detail.casefold() or "supplier invoice" in detail.casefold()
    return IntegrationDeliveryError(
        "ERPNext rejected the invoice draft",
        code="erpnext_duplicate_invoice" if duplicate else "erpnext_validation_rejected",
        retryable=False,
    )


def _safe_error_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "request rejected"
    if not isinstance(payload, dict):
        return "request rejected"
    values = (
        payload.get("exc_type"),
        payload.get("exception"),
        payload.get("message"),
        payload.get("_server_messages"),
    )
    return " ".join(str(value) for value in values if value)[:500]
