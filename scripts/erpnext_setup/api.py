from __future__ import annotations

import json
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


class ERPNextAPIError(RuntimeError):
    """A sanitized ERPNext API failure."""


class ERPNextAdminClient:
    def __init__(self, base_url: str, *, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def login(self, password: str) -> None:
        response = self._request(
            "POST",
            "/api/method/login",
            form={"usr": "Administrator", "pwd": password},
        )
        if response.get("message") != "Logged In":
            raise ERPNextAPIError("ERPNext Administrator login returned an unexpected response.")

    def logout(self) -> None:
        self._request("POST", "/api/method/logout")

    def call_method(self, method: str, *, values: dict[str, Any] | None = None) -> Any:
        response = self._request("POST", f"/api/method/{method}", form=values or {})
        return response.get("message")

    def list_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: tuple[str, ...] = ("name",),
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        query = urlencode(
            {
                "filters": json.dumps(filters or {}, separators=(",", ":")),
                "fields": json.dumps(fields, separators=(",", ":")),
                "limit_page_length": str(limit),
            }
        )
        response = self._request("GET", f"/api/resource/{quote(doctype, safe='')}?{query}")
        data = response.get("data", [])
        if not isinstance(data, list):
            raise ERPNextAPIError(f"ERPNext returned invalid list data for {doctype}.")
        return data

    def get_document(self, doctype: str, name: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise ERPNextAPIError(f"ERPNext returned invalid document data for {doctype}.")
        return data

    def create_document(self, doctype: str, values: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/resource/{quote(doctype, safe='')}",
            payload=values,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise ERPNextAPIError(f"ERPNext returned invalid create data for {doctype}.")
        return data

    def update_document(self, doctype: str, name: str, values: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "PUT",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
            payload=values,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise ERPNextAPIError(f"ERPNext returned invalid update data for {doctype}.")
        return data

    def delete_document(self, doctype: str, name: str) -> None:
        self._request(
            "DELETE",
            f"/api/resource/{quote(doctype, safe='')}/{quote(name, safe='')}",
        )

    def find_one(
        self,
        doctype: str,
        filters: dict[str, Any],
        *,
        fields: tuple[str, ...] = ("name",),
    ) -> dict[str, Any] | None:
        rows = self.list_documents(doctype, filters=filters, fields=fields, limit=2)
        if len(rows) > 1:
            raise ERPNextAPIError(f"Expected one {doctype} for {filters}, found {len(rows)}.")
        return rows[0] if rows else None

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        elif form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urlencode(form).encode("utf-8")

        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _safe_http_detail(exc)
            raise ERPNextAPIError(f"ERPNext HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ERPNextAPIError(f"ERPNext request failed: {type(exc).__name__}") from exc
        if not isinstance(parsed, dict):
            raise ERPNextAPIError("ERPNext returned a non-object JSON response.")
        return parsed


def _safe_http_detail(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "request rejected"
    if not isinstance(payload, dict):
        return "request rejected"
    return str(payload.get("exception") or payload.get("exc_type") or "request rejected")[:300]
