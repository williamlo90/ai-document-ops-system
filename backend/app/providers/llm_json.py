from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.extraction.schemas import FieldConfidence, InvoiceData, InvoiceExtraction, InvoiceLineItem
from app.providers.contracts import ExtractionResult, ParsedDocument, ProviderError


PostJson = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class LlmJsonInvoiceExtractor:
    api_key: str
    endpoint: str
    model: str
    timeout_seconds: int = 60
    post_json: PostJson = None

    provider_name: str = "llm_json"

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("EXTRACTOR_API_KEY is required when EXTRACTOR_PROVIDER=llm_json")
        if not self.endpoint:
            raise ValueError("EXTRACTOR_ENDPOINT is required when EXTRACTOR_PROVIDER=llm_json")
        if not self.model:
            raise ValueError("EXTRACTOR_MODEL is required when EXTRACTOR_PROVIDER=llm_json")
        if self.timeout_seconds <= 0:
            raise ValueError("PROVIDER_TIMEOUT_SECONDS must be greater than zero")
        if self.post_json is None:
            object.__setattr__(
                self,
                "post_json",
                lambda url, payload, headers: _post_json(
                    url,
                    payload,
                    headers,
                    timeout_seconds=self.timeout_seconds,
                ),
            )

    def extract_invoice(self, parsed_document: ParsedDocument) -> ExtractionResult:
        try:
            response = self.post_json(
                self.endpoint,
                _payload(self.model, parsed_document.text),
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            data = _extract_json_object(response)
            _reject_empty_invoice_payload(data)
            extraction = InvoiceExtraction(
                data=_ground_vendor(_invoice_data(data), parsed_document.text),
                confidence=_field_confidence(data.get("field_confidence")),
            )
        except ProviderError:
            raise
        except (InvalidOperation, TypeError, ValueError, KeyError) as exc:
            raise ProviderError("invalid_extractor_response", self.provider_name) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise ProviderError(
                "extractor_request_failed", self.provider_name, retryable=True
            ) from exc
        return ExtractionResult(
            extraction=extraction,
            provider_name=self.provider_name,
            provider_trace_id=parsed_document.provider_trace_id,
        )


def _payload(model: str, text: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract invoice fields from OCR text. Return only valid JSON with keys: "
                    "vendor_name, invoice_number, invoice_date, due_date, subtotal, tax, "
                    "total, currency, line_items, field_confidence. "
                    "Dates must be YYYY-MM-DD. "
                    "Money and quantities must be JSON strings or numbers. "
                    "field_confidence must be a list of objects, each containing 'field_name' and 'score'. "
                    "Rules: (1) Ignore common OCR typos: letter O vs digit 0, letter l vs digit 1. "
                    "(2) Normalise any date format to YYYY-MM-DD, even if partially garbled. "
                    "(3) If tax appears as a negative or is embedded in a total row, extract it as the absolute value. "
                    "(4) If a line_item amount is missing, compute it as quantity * unit_price. "
                    "(5) Never infer or guess a field that is not explicitly present; return null. "
                    "(6) vendor_name must be explicitly identified as the seller, supplier, or FROM "
                    "party; do not use a platform header, document title, or bill-to recipient. "
                    "(7) invoice_date must come from an explicitly labeled invoice or issue date; "
                    "do not derive it from a due date, invoice number, or unrelated date. "
                    "(8) If no tax label and amount are present, return null rather than zero."
                ),
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    # Some hosted LLM gateways reject requests without a User-Agent.
    final_headers = {"User-Agent": "DocIntel-MVP/1.0"}
    final_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=final_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            "extractor_http_error", "llm_json", retryable=exc.code == 429 or exc.code >= 500
        ) from exc


def _extract_json_object(response: dict[str, Any]) -> dict[str, Any]:
    if isinstance(response.get("data"), dict):
        return response["data"]
    if isinstance(response.get("output_text"), str):
        return _loads_object(response["output_text"])
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return _loads_object(content)
    return response


def _loads_object(text: str) -> dict[str, Any]:
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("Extractor response must be a JSON object")
    return loaded


def _invoice_data(data: dict[str, Any]) -> InvoiceData:
    if not isinstance(data, dict):
        raise ValueError("Extractor data must be an object")
    return InvoiceData(
        vendor_name=_text(data.get("vendor_name")),
        invoice_number=_text(data.get("invoice_number")),
        invoice_date=_date(data.get("invoice_date")),
        due_date=_date(data.get("due_date")),
        subtotal=_decimal(data.get("subtotal")),
        tax=_decimal(data.get("tax")),
        total=_decimal(data.get("total")),
        currency=_text(data.get("currency")),
        line_items=_line_items(data.get("line_items")),
    )


def _ground_vendor(invoice: InvoiceData, source_text: str) -> InvoiceData:
    if invoice.vendor_name is None or _has_vendor_context(source_text, invoice.vendor_name):
        return invoice
    return replace(invoice, vendor_name=None)


def _has_vendor_context(source_text: str, vendor_name: str) -> bool:
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    normalized_vendor = _searchable_text(vendor_name)
    for index, line in enumerate(lines):
        if normalized_vendor not in _searchable_text(line):
            continue
        before = " ".join(lines[max(0, index - 2) : index + 1])
        after = " ".join(lines[index : index + 3])
        if re.search(r"\b(from|seller|supplier|vendor)\b", before, flags=re.IGNORECASE):
            return True
        if re.search(
            r"(@|\b(vat|tax id|registration)\b|\b\d+\s+[^\n]*(street|st|road|rd|avenue|ave|boulevard|blvd|lane|ln)\b)",
            after,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def _searchable_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _reject_empty_invoice_payload(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("Extractor data must be an object")
    invoice_fields = (
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax",
        "total",
        "currency",
    )
    if not any(_text(data.get(field_name)) for field_name in invoice_fields):
        raise ValueError("Extractor response did not include invoice fields")


def _line_items(value: Any) -> tuple[InvoiceLineItem, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ValueError("line_items must be a list")
    return tuple(
        InvoiceLineItem(
            description=_text(item.get("description")),
            quantity=_decimal(item.get("quantity")),
            unit_price=_decimal(item.get("unit_price")),
            amount=_decimal(item.get("amount")),
        )
        for item in value
        if isinstance(item, dict)
    )


def _field_confidence(value: Any) -> tuple[FieldConfidence, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ValueError("field_confidence must be a list")
    return tuple(
        FieldConfidence(
            field_name=str(item["field_name"]),
            score=_decimal(item.get("score")),
            source_page=int(item["source_page"]) if item.get("source_page") is not None else None,
            source_text=_text(item.get("source_text")),
        )
        for item in value
        if isinstance(item, dict) and item.get("field_name")
    )


def _date(value: Any) -> date | None:
    text = _text(value)
    return date.fromisoformat(text) if text else None


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None
