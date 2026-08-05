from __future__ import annotations

from app.benchmark.datasets import Scenario
from app.benchmark.metrics import BenchmarkMetrics
from app.evaluation.invoice import evaluate_invoice
from app.providers.contracts import InvoiceExtractionProvider


def run_benchmark(extractor: InvoiceExtractionProvider, scenarios: tuple[Scenario, ...]) -> BenchmarkMetrics:
    results = [evaluate_invoice(item.expected, extractor.extract(item.pdf).data) for item in scenarios]
    return BenchmarkMetrics(
        scenario_count=len(results),
        mean_field_match=sum(item.field_match for item in results) / len(results),
        validation_accuracy=sum(item.validation_match for item in results) / len(results),
    )
