from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    provider: str
    validation_errors: tuple[str, ...]
