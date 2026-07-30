from __future__ import annotations

import hashlib
import json
from uuid import UUID

from app.backoffice.errors import BackofficeWorkflowError
from app.backoffice.models import WorkType
from app.backoffice.planner import PlanningInput
from app.core.security import SecurityContext


def normalized_key(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if len(normalized) > 200:
        raise BackofficeWorkflowError("Idempotency key is too long.")
    return normalized


def work_item_fingerprint(
    *,
    title: str,
    work_type: WorkType | None,
    linked_document_ids: tuple[UUID, ...],
    business_context: dict[str, str],
) -> str:
    return fingerprint(
        {
            "title": title,
            "work_type": work_type.value if work_type else None,
            "linked_document_ids": [str(value) for value in linked_document_ids],
            "business_context": business_context,
        }
    )


def planning_fingerprint(inputs: PlanningInput, context: SecurityContext) -> str:
    return fingerprint(
        {
            "requested_outcome": inputs.requested_outcome,
            "evidence_sufficient": inputs.evidence_sufficient,
            "approved_for_export": inputs.approved_for_export,
            "missing_fields": list(inputs.missing_fields),
            "selected_document_id": (
                str(inputs.selected_document_id) if inputs.selected_document_id else None
            ),
            "role": context.role,
            "is_admin": context.is_admin,
        }
    )


def fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_matching_fingerprint(actual: str | None, expected: str) -> None:
    if actual != expected:
        raise BackofficeWorkflowError(
            "This idempotency key is already bound to a different request."
        )
