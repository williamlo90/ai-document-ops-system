from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from app.providers.contracts import DocumentSource, ParsedDocument, ParsedPage, ProviderError


PostJson = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class MistralOcrParserProvider:
    api_key: str
    endpoint: str
    model: str
    post_json: PostJson = None

    provider_name: str = "mistral_ocr"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is required when PARSER_PROVIDER=mistral_ocr")
        if self.post_json is None:
            object.__setattr__(self, "post_json", _post_json)

    def parse(self, source: DocumentSource) -> ParsedDocument:
        payload = {
            "model": self.model,
            "document": {
                "type": "document_url",
                "document_url": _pdf_data_url(source.path.read_bytes()),
            },
        }
        try:
            data = self.post_json(
                self.endpoint,
                payload,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except (OSError, urllib.error.URLError) as exc:
            raise ProviderError("ocr_request_failed", self.provider_name, retryable=True) from exc
        return _parsed_document(data, source.storage_key, self.provider_name)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            "ocr_http_error", "mistral_ocr", retryable=exc.code == 429 or exc.code >= 500
        ) from exc


def _pdf_data_url(content: bytes) -> str:
    encoded = base64.b64encode(content).decode()
    return f"data:application/pdf;base64,{encoded}"


def _parsed_document(
    data: dict[str, Any],
    fallback_trace_id: str,
    provider_name: str,
) -> ParsedDocument:
    pages_data = data.get("pages") or []
    pages = tuple(
        ParsedPage(
            page_number=int(page.get("index", index) or index) + 1,
            text=str(page.get("markdown") or page.get("text") or ""),
        )
        for index, page in enumerate(pages_data)
    )
    text = "\n\n".join(page.text for page in pages).strip()
    if not text:
        text = str(data.get("markdown") or data.get("text") or "").strip()
    return ParsedDocument(
        text=text,
        pages=pages,
        provider_name=provider_name,
        provider_trace_id=str(data.get("id") or data.get("trace_id") or fallback_trace_id),
    )
