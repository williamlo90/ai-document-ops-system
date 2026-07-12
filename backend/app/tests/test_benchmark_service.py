from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from app.benchmark.datasets import load_evaluation_dataset
from app.benchmark.models import EvaluationDataset, EvaluationDocument
from app.benchmark.service import invoice_data_to_fields, run_dataset
from app.extraction.schemas import InvoiceData, InvoiceExtraction
from app.providers.contracts import (
    DocumentSource,
    ExtractionResult,
    ParsedDocument,
    ProviderError,
)


class RecordingParser:
    provider_name = "recording_parser"

    def __init__(
        self, *, fail_on: set[str] | None = None, empty_on: set[str] | None = None
    ) -> None:
        self.fail_on = fail_on or set()
        self.empty_on = empty_on or set()
        self.sources: list[DocumentSource] = []

    def parse(self, source: DocumentSource) -> ParsedDocument:
        self.sources.append(source)
        if source.storage_key in self.fail_on:
            raise ProviderError("parser_failed", self.provider_name)
        text = "" if source.storage_key in self.empty_on else f"text for {source.storage_key}"
        return ParsedDocument(
            text=text,
            provider_name=self.provider_name,
            provider_trace_id=f"trace-{source.storage_key}",
        )


class StaticExtractor:
    provider_name = "static_extractor"

    def __init__(self, *, fail_on_trace: set[str] | None = None) -> None:
        self.fail_on_trace = fail_on_trace or set()

    def extract_invoice(self, parsed_document: ParsedDocument) -> ExtractionResult:
        if parsed_document.provider_trace_id in self.fail_on_trace:
            raise ProviderError("extractor_failed", self.provider_name)
        return ExtractionResult(
            extraction=InvoiceExtraction(
                data=InvoiceData(
                    vendor_name="Acme Logistics",
                    invoice_number="INV-001",
                    invoice_date=date(2026, 6, 18),
                    due_date=date(2026, 7, 18),
                    subtotal=Decimal("100.00"),
                    tax=Decimal("10.00"),
                    total=Decimal("110.00"),
                    currency="USD",
                )
            ),
            provider_name=self.provider_name,
            provider_trace_id=parsed_document.provider_trace_id,
        )


class BenchmarkRunnerTests(unittest.TestCase):
    def test_run_dataset_uses_document_source_path_and_returns_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "invoice-001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dataset = EvaluationDataset(
                name="unit",
                documents=(
                    EvaluationDocument(
                        document_id="invoice-001",
                        expected_fields={"total": "110.00"},
                        source_path=source,
                    ),
                ),
            )
            parser = RecordingParser()

            run = run_dataset(dataset, parser, StaticExtractor(), rate_limit_s=0)

            self.assertEqual(run.dataset_name, "unit")
            self.assertEqual(run.provider_name, "recording_parser+static_extractor")
            self.assertEqual(len(run.results), 1)
            self.assertEqual(parser.sources[0].path, source)
            self.assertEqual(parser.sources[0].storage_key, "invoice-001")
            self.assertEqual(run.results[0].predicted_fields["total"], "110.00")
            self.assertIsNone(run.results[0].error)
            self.assertEqual(run.results[0].trace_id, "trace-invoice-001")
            self.assertGreaterEqual(run.results[0].latency_ms, 0.0)

    def test_provider_error_is_recorded_without_stopping_run(self) -> None:
        dataset = EvaluationDataset(
            name="unit",
            documents=(
                EvaluationDocument("ok", {"total": "110.00"}),
                EvaluationDocument("bad", {"total": "110.00"}),
                EvaluationDocument("after", {"total": "110.00"}),
            ),
        )
        parser = RecordingParser(fail_on={"bad"})

        run = run_dataset(dataset, parser, StaticExtractor(), rate_limit_s=0)

        self.assertEqual(len(run.results), 3)
        self.assertIsNone(run.results[0].error)
        self.assertEqual(run.results[1].error, "parser_failed")
        self.assertIsNone(run.results[2].error)

    def test_empty_parsed_text_is_recorded_as_failed_result(self) -> None:
        dataset = EvaluationDataset(
            name="unit",
            documents=(EvaluationDocument("empty", {"total": "110.00"}),),
        )
        parser = RecordingParser(empty_on={"empty"})

        run = run_dataset(dataset, parser, StaticExtractor(), rate_limit_s=0)

        self.assertEqual(run.results[0].error, "empty_parsed_text")
        self.assertEqual(run.results[0].predicted_fields, {})

    def test_rate_limit_sleep_is_applied_between_documents(self) -> None:
        dataset = EvaluationDataset(
            name="unit",
            documents=(
                EvaluationDocument("a", {"total": "110.00"}),
                EvaluationDocument("b", {"total": "110.00"}),
                EvaluationDocument("c", {"total": "110.00"}),
            ),
        )

        with patch("app.benchmark.service.time.sleep") as sleep:
            run_dataset(dataset, RecordingParser(), StaticExtractor(), rate_limit_s=0.5)

        self.assertEqual(sleep.call_count, 2)
        sleep.assert_any_call(0.5)

    def test_load_dataset_supports_expected_json_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "expected.json").write_text(
                """
                [
                  {
                    "document_id": "invoice-001",
                    "vendor_name": "Acme Logistics",
                    "invoice_number": "INV-001",
                    "invoice_date": "2026-06-18",
                    "due_date": "2026-07-18",
                    "subtotal": "100.00",
                    "tax": "10.00",
                    "total": "110.00",
                    "currency": "USD"
                  }
                ]
                """,
                encoding="utf-8",
            )

            dataset = load_evaluation_dataset(root)

            self.assertEqual(dataset.name, root.name)
            self.assertEqual(dataset.documents[0].document_id, "invoice-001")

    def test_invoice_data_to_fields_serializes_dates_and_money(self) -> None:
        fields = invoice_data_to_fields(
            InvoiceData(
                vendor_name="Vendor",
                invoice_number="INV-9",
                invoice_date=date(2026, 1, 2),
                due_date=date(2026, 2, 3),
                subtotal=Decimal("10.00"),
                tax=Decimal("1.50"),
                total=Decimal("11.50"),
                currency="USD",
            )
        )

        self.assertEqual(fields["invoice_date"], "2026-01-02")
        self.assertEqual(fields["due_date"], "2026-02-03")
        self.assertEqual(fields["subtotal"], "10.00")
        self.assertEqual(fields["total"], "11.50")


if __name__ == "__main__":
    unittest.main()
