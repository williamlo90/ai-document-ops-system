from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.benchmark.datasets import load_evaluation_dataset
from app.benchmark.models import (
    BenchmarkRun,
    EvaluationDataset,
    EvaluationDocument,
    ProviderRunResult,
)
from app.providers.contracts import (
    DocumentSource,
    ExtractorProvider,
    ParserProvider,
    ProviderError,
)
from app.extraction.schemas import InvoiceData


def load_dataset(dataset_path: str | Path) -> EvaluationDataset:
    return load_evaluation_dataset(dataset_path)


def run_dataset(
    dataset: EvaluationDataset,
    parser: ParserProvider,
    extractor: ExtractorProvider,
    *,
    rate_limit_s: float = 0.2,
) -> BenchmarkRun:
    started_at = _now()
    results: list[ProviderRunResult] = []
    for index, doc in enumerate(dataset.documents):
        if index > 0 and rate_limit_s > 0:
            time.sleep(rate_limit_s)
        result = _run_document(doc, parser, extractor)
        results.append(result)
    finished_at = _now()
    return BenchmarkRun(
        dataset_name=dataset.name,
        provider_name=f"{parser.provider_name}+{extractor.provider_name}",
        results=tuple(results),
        started_at=started_at,
        finished_at=finished_at,
    )


def _run_document(
    doc: EvaluationDocument,
    parser: ParserProvider,
    extractor: ExtractorProvider,
) -> ProviderRunResult:
    predicted_fields: dict[str, str | None] = {}
    latency_ms = 0.0
    error: str | None = None
    trace_id: str | None = None

    try:
        start = time.perf_counter()
        parsed = parser.parse(_document_source(doc))
        latency_ms += (time.perf_counter() - start) * 1000
        trace_id = parsed.provider_trace_id

        if parsed.text:
            start = time.perf_counter()
            extraction = extractor.extract_invoice(parsed)
            latency_ms += (time.perf_counter() - start) * 1000
            predicted_fields = invoice_data_to_fields(extraction.extraction.data)
            trace_id = extraction.provider_trace_id or trace_id
        else:
            error = "empty_parsed_text"
    except ProviderError as e:
        error = str(e)
    except Exception:
        error = f"Provider failed: {parser.provider_name}+{extractor.provider_name}"

    return ProviderRunResult(
        document_id=doc.document_id,
        provider_name=f"{parser.provider_name}+{extractor.provider_name}",
        predicted_fields=predicted_fields,
        latency_ms=latency_ms,
        error=error,
        trace_id=trace_id,
    )


def invoice_data_to_fields(data: InvoiceData) -> dict[str, Any]:
    return {
        "vendor_name": data.vendor_name,
        "invoice_number": data.invoice_number,
        "invoice_date": data.invoice_date.isoformat() if data.invoice_date else None,
        "due_date": data.due_date.isoformat() if data.due_date else None,
        "subtotal": str(data.subtotal) if data.subtotal is not None else None,
        "tax": str(data.tax) if data.tax is not None else None,
        "total": str(data.total) if data.total is not None else None,
        "currency": data.currency,
    }


def _document_source(doc: EvaluationDocument) -> DocumentSource:
    source_path = doc.source_path or Path(f"{doc.document_id}.pdf")
    return DocumentSource(
        storage_key=doc.document_id,
        path=source_path,
        original_filename=source_path.name,
        content_type="application/pdf",
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
