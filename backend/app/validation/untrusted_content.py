from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UntrustedDocumentText:
    text: str


def bounded_evidence(text: str, limit: int = 500) -> UntrustedDocumentText:
    return UntrustedDocumentText(text=text[:limit])
