from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPORTED = "exported"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.QUEUED}),
    DocumentStatus.QUEUED: frozenset({DocumentStatus.PROCESSING, DocumentStatus.CANCELLED}),
    DocumentStatus.PROCESSING: frozenset(
        {DocumentStatus.QUEUED, DocumentStatus.EXTRACTED, DocumentStatus.FAILED}
    ),
    DocumentStatus.EXTRACTED: frozenset(
        {
            DocumentStatus.QUEUED,
            DocumentStatus.APPROVED,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.FAILED,
        }
    ),
    DocumentStatus.NEEDS_REVIEW: frozenset(
        {DocumentStatus.QUEUED, DocumentStatus.APPROVED, DocumentStatus.REJECTED}
    ),
    DocumentStatus.APPROVED: frozenset({DocumentStatus.EXPORTED}),
    DocumentStatus.REJECTED: frozenset(),
    DocumentStatus.FAILED: frozenset({DocumentStatus.QUEUED, DocumentStatus.CANCELLED}),
    DocumentStatus.EXPORTED: frozenset(),
    DocumentStatus.CANCELLED: frozenset({DocumentStatus.QUEUED}),
}

EDITABLE_INTAKE_STATUSES = frozenset(
    {
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,
        DocumentStatus.PROCESSING,
        DocumentStatus.EXTRACTED,
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.FAILED,
        DocumentStatus.CANCELLED,
    }
)


class InvalidStatusTransition(ValueError):
    pass


class IntakeDraftLocked(ValueError):
    pass


def can_transition(current: DocumentStatus, target: DocumentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def require_transition(current: DocumentStatus, target: DocumentStatus) -> None:
    if not can_transition(current, target):
        raise InvalidStatusTransition(f"Cannot transition document from {current} to {target}")


def require_intake_editable(status: DocumentStatus) -> None:
    if status not in EDITABLE_INTAKE_STATUSES:
        raise IntakeDraftLocked(f"Cannot edit intake draft while document is {status}")
