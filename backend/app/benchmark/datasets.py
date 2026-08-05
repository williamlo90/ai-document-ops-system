from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.benchmark.models import EvaluationDataset, EvaluationDocument
from app.evaluation.invoice import EVALUATED_FIELDS


REQUIRED_EXPECTED_FIELDS = tuple(EVALUATED_FIELDS)
PRIVATE_PATH_PARTS = {"uploads", "data"}


class DatasetValidationError(ValueError):
    pass


def load_evaluation_dataset(dataset_path: str | Path) -> EvaluationDataset:
    root = Path(dataset_path).resolve()
    _ensure_safe_dataset_root(root)
    expected_file = root / "expected.json"
    if not expected_file.is_file():
        raise FileNotFoundError(f"Dataset expected.json not found at {expected_file}")

    try:
        raw_records = json.loads(expected_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"Invalid dataset JSON: {expected_file}") from exc

    if not isinstance(raw_records, list):
        raise DatasetValidationError("Dataset expected.json must contain a list of records.")

    documents = tuple(
        _record_to_document(root, index, record) for index, record in enumerate(raw_records)
    )
    if not documents:
        raise DatasetValidationError("Dataset must contain at least one expected record.")

    _ensure_unique_document_ids(documents)
    return EvaluationDataset(name=root.name, documents=documents, root_path=root)


def records_from_dataset(dataset: EvaluationDataset) -> list[dict[str, Any]]:
    return [
        {
            "document_id": document.document_id,
            **document.expected_fields,
        }
        for document in dataset.documents
    ]


def _record_to_document(root: Path, index: int, record: Any) -> EvaluationDocument:
    if not isinstance(record, dict):
        raise DatasetValidationError(f"Expected record at index {index} must be an object.")

    document_id = record.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        raise DatasetValidationError(f"Expected record at index {index} must include document_id.")

    missing = [field for field in REQUIRED_EXPECTED_FIELDS if field not in record]
    if missing:
        raise DatasetValidationError(
            f"Expected record {document_id} is missing fields: {', '.join(missing)}"
        )

    source_path = _safe_source_path(root, record.get("source_file"), document_id)
    expected_fields = {
        key: value for key, value in record.items() if key not in {"document_id", "source_file"}
    }
    return EvaluationDocument(
        document_id=document_id.strip(),
        expected_fields=expected_fields,
        source_path=source_path,
    )


def _safe_source_path(root: Path, source_file: Any, document_id: str) -> Path | None:
    if source_file in (None, ""):
        return None
    if not isinstance(source_file, str):
        raise DatasetValidationError(f"source_file for {document_id} must be a string.")

    candidate = (root / source_file).resolve()
    if not _is_relative_to(candidate, root):
        raise DatasetValidationError(f"source_file for {document_id} must stay inside the dataset.")
    if _has_private_path_part(candidate):
        raise DatasetValidationError(f"source_file for {document_id} points to a private path.")
    if not candidate.is_file():
        raise DatasetValidationError(f"source_file for {document_id} does not exist: {source_file}")
    return candidate


def _ensure_unique_document_ids(documents: tuple[EvaluationDocument, ...]) -> None:
    seen: set[str] = set()
    for document in documents:
        if document.document_id in seen:
            raise DatasetValidationError(f"Duplicate document_id: {document.document_id}")
        seen.add(document.document_id)


def _ensure_safe_dataset_root(root: Path) -> None:
    if _has_private_path_part(root):
        raise DatasetValidationError(
            "Dataset path must not be inside a private data/upload folder."
        )


def _has_private_path_part(path: Path) -> bool:
    parts = {part.casefold() for part in path.parts}
    return bool(parts & PRIVATE_PATH_PARTS and "examples" not in parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
