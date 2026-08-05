from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Citation:
    document_id: UUID
    field_name: str
    value: str


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    text: str
    citations: tuple[Citation, ...]
    abstained: bool = False
