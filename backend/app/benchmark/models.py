from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvaluationDocument:
    document_id: str
    expected_fields: dict[str, Any]
    source_path: Path | None = None


@dataclass(frozen=True)
class EvaluationDataset:
    name: str
    documents: tuple[EvaluationDocument, ...]
    root_path: Path | None = None


@dataclass(frozen=True)
class ProviderRunResult:
    document_id: str
    provider_name: str
    predicted_fields: dict[str, str | None]
    latency_ms: float
    error: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True)
class BenchmarkRun:
    dataset_name: str
    provider_name: str
    results: tuple[ProviderRunResult, ...]
    started_at: datetime
    finished_at: datetime


def dataset_from_fixtures(name: str, records: list[dict[str, Any]]) -> EvaluationDataset:
    documents = tuple(
        EvaluationDocument(
            document_id=str(record["document_id"]),
            expected_fields={
                k: record[k] for k in record if k not in {"document_id", "source_file"}
            },
        )
        for record in records
    )
    return EvaluationDataset(name=name, documents=documents)


def run_results_to_predicted_records(
    results: tuple[ProviderRunResult, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "document_id": r.document_id,
            **{k: v for k, v in r.predicted_fields.items()},
        }
        for r in results
    ]
