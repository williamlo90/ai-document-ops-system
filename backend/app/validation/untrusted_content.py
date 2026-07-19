from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.extraction.schemas import FieldConfidence, InvoiceExtraction
from app.providers.contracts import ParsedDocument
from app.validation.invoice import IssueSeverity, ValidationIssue


EVIDENCE_REQUIRED_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "total",
    "currency",
)

PROMPT_INJECTION_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions?\b",
        r"\bdisregard\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|rules?)\b",
        r"\b(?:system|developer|assistant)\s+(?:message|prompt)\s*:",
        r"\b(?:reveal|repeat|print|return)\s+(?:the\s+)?system\s+prompt\b",
        r"\b(?:set|replace|override|change)\s+(?:the\s+)?(?:vendor_name|invoice_number|invoice_date|total|currency)\s+(?:to|with)\b",
        r"\b(?:call|invoke|execute|run)\s+(?:the\s+)?(?:tool|function|command)\b",
        r"\breturn\s+(?:only\s+)?(?:this\s+)?json\b",
    )
)


def validate_untrusted_extraction(
    extraction: InvoiceExtraction,
    parsed_document: ParsedDocument,
    provider_name: str,
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if contains_prompt_injection(parsed_document.text):
        issues.append(
            ValidationIssue(
                field_name="document",
                severity=IssueSeverity.ERROR,
                code="potential_prompt_injection",
                message=(
                    "The PDF contains text that looks like instructions to the AI. "
                    "Verify the invoice manually and correct its fields before approval."
                ),
            )
        )
    if provider_name != "llm_json":
        return tuple(issues)
    for field_name in EVIDENCE_REQUIRED_FIELDS:
        value = getattr(extraction.data, field_name)
        if value is None:
            continue
        evidence = tuple(item for item in extraction.confidence if item.field_name == field_name)
        if any(_supports_value(item, value, parsed_document) for item in evidence):
            continue
        issues.append(
            ValidationIssue(
                field_name=field_name,
                severity=IssueSeverity.ERROR,
                code="missing_field_evidence",
                message=(
                    "This AI value has no matching PDF excerpt. Verify or correct it before approval."
                ),
            )
        )
    return tuple(issues)


def contains_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in PROMPT_INJECTION_PATTERNS)


def _supports_value(
    evidence: FieldConfidence,
    value: str | date | Decimal,
    parsed_document: ParsedDocument,
) -> bool:
    if evidence.source_page is None or not evidence.source_text:
        return False
    page_text = _page_text(parsed_document, evidence.source_page)
    if evidence.source_text not in page_text:
        return False
    if isinstance(value, date):
        return value in _dates_in_text(evidence.source_text)
    if isinstance(value, Decimal):
        return any(candidate == value for candidate in _decimals_in_text(evidence.source_text))
    normalized_value = _searchable(value)
    return bool(normalized_value) and normalized_value in _searchable(evidence.source_text)


def _page_text(parsed_document: ParsedDocument, page_number: int) -> str:
    if not parsed_document.pages:
        return parsed_document.text if page_number == 1 else ""
    return next(
        (page.text for page in parsed_document.pages if page.page_number == page_number),
        "",
    )


def _dates_in_text(text: str) -> set[date]:
    candidates: set[date] = set()
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y")
    for raw in re.findall(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b", text):
        for date_format in formats:
            try:
                candidates.add(datetime.strptime(raw, date_format).date())
                break
            except ValueError:
                continue
    return candidates


def _decimals_in_text(text: str) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for raw in re.findall(r"-?\d[\d,. ]*\d|-?\d", text):
        normalized = raw.replace(" ", "")
        if "," in normalized and "." in normalized:
            normalized = (
                normalized.replace(".", "").replace(",", ".")
                if normalized.rfind(",") > normalized.rfind(".")
                else normalized.replace(",", "")
            )
        elif "," in normalized:
            tail = normalized.rsplit(",", 1)[-1]
            normalized = normalized.replace(",", "." if len(tail) == 2 else "")
        try:
            values.append(Decimal(normalized))
        except InvalidOperation:
            continue
    return tuple(values)


def _searchable(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))
