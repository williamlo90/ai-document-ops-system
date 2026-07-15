from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.extraction.schemas import InvoiceData


CORRECTION_SCHEMA_VERSION = "reviewer_correction_v1"


class CorrectionSource(StrEnum):
    INTAKE_CHECK = "intake_check"
    REVIEWER_EDIT = "reviewer_edit"


class CorrectionReasonSource(StrEnum):
    USER = "user"
    REVIEWER_REQUEST = "reviewer_request"
    SYSTEM_DEFAULT = "system_default"


CorrectionValue = str | int | float | bool | None


@dataclass(frozen=True)
class FieldCorrection:
    field_path: str
    original_ai_value: CorrectionValue
    before_value: CorrectionValue
    after_value: CorrectionValue


@dataclass(frozen=True)
class CorrectionEvent:
    workspace_id: str
    document_id: UUID
    actor: str
    reason: str
    source: CorrectionSource
    reason_source: CorrectionReasonSource
    original_ai_data: InvoiceData
    before_data: InvoiceData
    after_data: InvoiceData
    changes: tuple[FieldCorrection, ...]
    schema_version: str = CORRECTION_SCHEMA_VERSION
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
