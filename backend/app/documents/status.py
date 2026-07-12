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


ALLOWED_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.UPLOADED: {DocumentStatus.QUEUED},
    DocumentStatus.QUEUED: {DocumentStatus.PROCESSING, DocumentStatus.CANCELLED},
    DocumentStatus.PROCESSING: {
        DocumentStatus.QUEUED,
        DocumentStatus.EXTRACTED,
        DocumentStatus.FAILED,
    },
    DocumentStatus.EXTRACTED: {
        DocumentStatus.QUEUED,
        DocumentStatus.APPROVED,
        DocumentStatus.NEEDS_REVIEW,
        DocumentStatus.FAILED,
    },
    DocumentStatus.NEEDS_REVIEW: {
        DocumentStatus.QUEUED,
        DocumentStatus.APPROVED,
        DocumentStatus.REJECTED,
    },
    DocumentStatus.APPROVED: {DocumentStatus.EXPORTED},
    DocumentStatus.REJECTED: set(),
    DocumentStatus.FAILED: {DocumentStatus.QUEUED, DocumentStatus.CANCELLED},
    DocumentStatus.EXPORTED: set(),
    DocumentStatus.CANCELLED: {DocumentStatus.QUEUED},
}


class InvalidStatusTransition(ValueError):
    pass


def can_transition(current: DocumentStatus, target: DocumentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def require_transition(current: DocumentStatus, target: DocumentStatus) -> None:
    if not can_transition(current, target):
        raise InvalidStatusTransition(f"Cannot transition document from {current} to {target}")
