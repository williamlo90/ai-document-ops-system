from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from app.review.corrections import correction_event_to_dict
from app.review.models import CorrectionEvent


def private_dataset_jsonl(events: Iterable[CorrectionEvent]) -> str:
    return "".join(
        f"{json.dumps(correction_event_to_dict(event), sort_keys=True)}\n" for event in events
    )


def sanitized_correction_summary(events: Iterable[CorrectionEvent]) -> dict[str, object]:
    records = list(events)
    fields = Counter(change.field_path for event in records for change in event.changes)
    sources = Counter(event.source.value for event in records)
    reason_sources = Counter(event.reason_source.value for event in records)
    change_count = sum(len(event.changes) for event in records)
    return {
        "schema_version": "correction_summary_v1",
        "privacy": "aggregate_only_no_document_ids_actors_reasons_or_values",
        "event_count": len(records),
        "document_count": len({event.document_id for event in records}),
        "changed_value_count": change_count,
        "field_change_counts": dict(sorted(fields.items())),
        "source_counts": dict(sorted(sources.items())),
        "reason_source_counts": dict(sorted(reason_sources.items())),
        "original_ai_snapshot_coverage": _ratio(
            sum(bool(event.original_ai_data) for event in records),
            len(records),
        ),
    }


def assert_private_dataset_path(path: Path, repository_root: Path) -> Path:
    resolved = path.expanduser().resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return resolved
    if not relative.parts or relative.parts[0] != "_private_data":
        raise ValueError(
            "Raw correction exports inside the repository must stay under _private_data/."
        )
    return resolved


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
