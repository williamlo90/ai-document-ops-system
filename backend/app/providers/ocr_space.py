from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from app.providers.contracts import (
    DocumentSource,
    ParsedDocument,
    ParsedPage,
    ProviderError,
    ProviderUsage,
)
from app.providers.http_transport import RejectRedirects


@dataclass(frozen=True)
class OcrSpaceParserProvider:
    api_key: str
    timeout_seconds: int = 60
    post_form: Callable | None = None
    provider_name: str = "ocr_space"

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("OCR_SPACE_API_KEY is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")

    def parse(self, source: DocumentSource) -> ParsedDocument:
        content = source.path.read_bytes()
        if source.content_type != "application/pdf" or not content.startswith(b"%PDF-"):
            raise ProviderError("ocr_space_requires_pdf", self.provider_name)
        if len(content) > 1_000_000:
            raise ProviderError("ocr_space_free_size_limit", self.provider_name)
        payload = {
            "base64Image": "data:application/pdf;base64," + base64.b64encode(content).decode(),
            "filetype": "PDF",
            "OCREngine": "2",
            "isTable": "true",
            "isOverlayRequired": "false",
        }
        endpoint = "https://api.ocr.space/parse/image"
        headers = {"apikey": self.api_key, "Content-Type": "application/x-www-form-urlencoded"}
        try:
            if self.post_form:
                data = self.post_form(endpoint, payload, headers)
            else:
                request = urllib.request.Request(
                    endpoint,
                    data=urllib.parse.urlencode(payload).encode(),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.build_opener(RejectRedirects()).open(
                    request, timeout=self.timeout_seconds
                ) as response:
                    data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                "ocr_http_error", self.provider_name, retryable=exc.code == 429 or exc.code >= 500
            ) from exc
        except (OSError, ValueError) as exc:
            raise ProviderError("ocr_request_failed", self.provider_name, retryable=True) from exc
        try:
            if data.get("IsErroredOnProcessing") is not False or data.get("OCRExitCode") != 1:
                raise ValueError("Failed or partial OCR")
            rows = data["ParsedResults"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
                raise ValueError("Missing pages or free page limit")
            pages = []
            for number, row in enumerate(rows, 1):
                if row.get("FileParseExitCode") != 1 or not isinstance(row.get("ParsedText"), str):
                    raise ValueError("Failed page")
                pages.append(ParsedPage(number, row["ParsedText"]))
            text = "\n\n".join(p.text for p in pages).strip()
            if not text:
                raise ValueError("Empty OCR")
            return ParsedDocument(
                text,
                tuple(pages),
                self.provider_name,
                source.storage_key,
                "ocr-space-engine-2",
                ProviderUsage(pages_processed=len(pages), document_size_bytes=len(content)),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderError("invalid_ocr_space_response", self.provider_name) from exc
