from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import re
from statistics import median
from dataclasses import dataclass, field
from threading import Lock, local
from time import monotonic
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
    api_key: str = field(repr=False)
    timeout_seconds: int = 60
    post_form: Callable | None = None
    engine: int = 2
    provider_name: str = "ocr_space"

    def __post_init__(self):
        if not self.api_key:
            raise ValueError("OCR_SPACE_API_KEY is required")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be positive")
        if self.engine not in (2, 3):
            raise ValueError("OCR.space engine must be 2 or 3")

    def parse(self, source: DocumentSource) -> ParsedDocument:
        content = source.path.read_bytes()
        if source.content_type != "application/pdf" or not content.startswith(b"%PDF-"):
            raise ProviderError("ocr_space_requires_pdf", self.provider_name)
        if len(content) > 1_000_000:
            raise ProviderError("ocr_space_free_size_limit", self.provider_name)
        payload = {
            "base64Image": "data:application/pdf;base64," + base64.b64encode(content).decode(),
            "filetype": "PDF",
            "OCREngine": str(self.engine),
            "isTable": "true",
            "isOverlayRequired": "true" if self.engine == 2 else "false",
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
            delay = None
            candidate = (exc.headers or {}).get("Retry-After")
            try:
                detail = json.loads(exc.read(4096))
                if isinstance(detail, dict) and detail.get("retryAfter") is not None:
                    candidate = detail["retryAfter"]
            except (ValueError, TypeError, OSError):
                pass
            try:
                if candidate is not None and 0 < float(candidate) <= 86400:
                    delay = float(candidate)
            except (ValueError, TypeError):
                pass
            raise ProviderError(
                "ocr_http_error",
                self.provider_name,
                retryable=exc.code == 429 or exc.code >= 500,
                http_status=exc.code,
                retry_after_seconds=delay,
            ) from exc
        except (OSError, ValueError) as exc:
            raise ProviderError("ocr_request_failed", self.provider_name, retryable=True) from exc
        try:
            message = data.get("ErrorMessage", "")
            if isinstance(message, list):
                message = " ".join(str(part)[:512] for part in message[:10])
            if isinstance(message, str) and re.search(
                r"(?:api\s*key).{0,40}(?:invalid|expired|not valid)|(?:invalid|expired).{0,40}(?:api\s*key)",
                message[:4096],
                re.I,
            ):
                raise ProviderError("ocr_auth_failed", self.provider_name, http_status=401)
            if data.get("IsErroredOnProcessing") is not False or data.get("OCRExitCode") != 1:
                raise ValueError("Failed or partial OCR")
            rows = data["ParsedResults"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 3:
                raise ValueError("Missing pages or free page limit")
            pages = []
            for number, row in enumerate(rows, 1):
                if row.get("FileParseExitCode") != 1 or not isinstance(row.get("ParsedText"), str):
                    raise ValueError("Failed page")
                pages.append(
                    ParsedPage(
                        number, _positional_table_text(row["ParsedText"], row.get("TextOverlay"))
                    )
                )
            text = "\n\n".join(p.text for p in pages).strip()
            if not text:
                raise ValueError("Empty OCR")
            return ParsedDocument(
                text,
                tuple(pages),
                self.provider_name,
                source.storage_key,
                f"ocr-space-engine-{self.engine}"
                + ("+positional-table-v1" if self.engine == 2 else "+markdown"),
                ProviderUsage(pages_processed=len(pages), document_size_bytes=len(content)),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ProviderError("invalid_ocr_space_response", self.provider_name) from exc


class OcrSpaceKeyPool:
    """Ordered, bounded failover; key cooldowns are shared across calls in this process."""

    provider_name = "ocr_space"

    def __init__(self, keys, timeout_seconds=60, *, engine=2, post_form=None, clock=monotonic):
        unique = tuple(dict.fromkeys(key.strip() for key in keys if key.strip()))
        if not unique or len(unique) > 10:
            raise ValueError("Configure between one and ten unique OCR.space keys")
        self._providers = tuple(
            OcrSpaceParserProvider(key, timeout_seconds, post_form, engine) for key in unique
        )
        self._cooldowns = [0.0] * len(unique)
        self._disabled = set()
        self._clock = clock
        self._lock = Lock()
        self._local = local()

    @property
    def last_attempts(self):
        return getattr(self._local, "attempts", [])

    def parse(self, source):
        self._local.attempts = []
        for index, provider in enumerate(self._providers):
            with self._lock:
                if index in self._disabled or self._cooldowns[index] > self._clock():
                    continue
            started = self._clock()
            try:
                result = provider.parse(source)
                self._local.attempts.append(
                    {
                        "credential_slot": index + 1,
                        "status": "succeeded",
                        "latency_ms": round((self._clock() - started) * 1000, 2),
                    }
                )
                return result
            except ProviderError as exc:
                self._local.attempts.append(
                    {
                        "credential_slot": index + 1,
                        "status": "failed",
                        "http_status": exc.http_status,
                        "retry_after_seconds": exc.retry_after_seconds,
                        "error_code": str(exc),
                        "latency_ms": round((self._clock() - started) * 1000, 2),
                    }
                )
                auth_failure = exc.http_status in {401, 403}
                if not auth_failure and not exc.retryable:
                    raise  # A malformed document/answer is not a credential failure.
                with self._lock:
                    if auth_failure:
                        self._disabled.add(index)
                    else:
                        delay = exc.retry_after_seconds or (60 if exc.http_status == 429 else 30)
                        self._cooldowns[index] = self._clock() + max(1, min(delay, 86400))
        with self._lock:
            waits = [
                max(0, self._cooldowns[i] - self._clock())
                for i in range(len(self._providers))
                if i not in self._disabled
            ]
        if not waits:
            raise ProviderError("ocr_keys_rejected", self.provider_name, http_status=401)
        raise ProviderError(
            "ocr_keys_cooling_down",
            self.provider_name,
            retryable=True,
            http_status=429,
            retry_after_seconds=max(1, min(waits)),
        )


def _positional_table_text(text: str, overlay) -> str:
    """Preserve unreadable table cells instead of shifting the next column left.

    Apply only to one fully identified five-column invoice table. Unsupported
    layouts retain the provider text; this function never supplies a missing word.
    """
    if not isinstance(overlay, dict) or not isinstance(overlay.get("Lines"), list):
        return text
    if len(overlay["Lines"]) > 1000:
        return text
    cells = []
    try:
        for line in overlay["Lines"]:
            words = line.get("Words", [])
            if not words or not line.get("LineText"):
                continue
            cells.append(
                {
                    "text": line["LineText"].strip(),
                    "x": min(float(w["Left"]) for w in words),
                    "y": min(float(w["Top"]) for w in words),
                    "h": max(float(w.get("Height", 12)) for w in words),
                }
            )
    except (ValueError, TypeError, KeyError):
        return text
    aliases = (
        {"description", "item"},
        {"uom", "unit"},
        {"quantity", "qty"},
        {"unit price", "rate"},
        {"line total", "amount"},
    )

    def normalize(value):
        return " ".join(value.lower().split())

    headers = []
    for names in aliases:
        matches = [cell for cell in cells if normalize(cell["text"]) in names]
        if len(matches) != 1:
            return text
        headers.append(matches[0])
    tolerance = max(6.0, median(cell["h"] for cell in headers) * 0.65)
    if max(cell["y"] for cell in headers) - min(cell["y"] for cell in headers) > tolerance:
        return text
    xs = [cell["x"] for cell in headers]
    if xs != sorted(xs) or len(set(xs)) != 5:
        return text
    y = max(cell["y"] for cell in headers)
    totals = {"subtotal", "sub total", "tax", "total", "total due", "grand total"}
    footer = min(
        (
            cell["y"]
            for cell in cells
            if cell["y"] > y + tolerance and normalize(cell["text"]) in totals
        ),
        default=None,
    )
    if footer is None:
        return text
    body = sorted(
        (cell for cell in cells if y + tolerance < cell["y"] < footer - tolerance),
        key=lambda cell: (cell["y"], cell["x"]),
    )
    groups = []
    for cell in body:
        if not groups or abs(cell["y"] - groups[-1][0]["y"]) > tolerance:
            groups.append([])
        groups[-1].append(cell)
    rows = []
    for group in groups:
        columns = [[] for _ in headers]
        for cell in group:
            column = min(range(5), key=lambda index: abs(cell["x"] - xs[index]))
            columns[column].append(cell)
        if not columns[0] or any(len(column) > 1 for column in columns[1:]):
            return text
        rows.append(
            [
                " ".join(cell["text"] for cell in sorted(column, key=lambda item: item["x"]))
                for column in columns
            ]
        )
    original = text.splitlines()
    starts = [
        i
        for i, line in enumerate(original)
        if all(
            any(re.search(rf"\b{re.escape(name)}\b", normalize(line)) for name in names)
            for names in aliases
        )
    ]
    if len(starts) != 1 or not rows:
        return text
    start = starts[0]
    end = next(
        (
            i
            for i in range(start + 1, len(original))
            if re.match(r"^\s*(subtotal|sub total|tax|total|grand total)\b", original[i], re.I)
        ),
        None,
    )
    if end is None:
        return text
    table = ["| Description | UOM | Quantity | Unit price | Amount |"]
    table.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([*original[:start], *table, *original[end:]])
