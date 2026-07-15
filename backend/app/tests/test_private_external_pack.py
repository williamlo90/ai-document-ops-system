from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.prepare_private_external_invoice_pack import _expected_fields  # noqa: E402
from scripts.run_private_external_evaluation import (  # noqa: E402
    _load_cached_observations,
    _run_document,
)

from app.extraction.schemas import InvoiceData, InvoiceExtraction  # noqa: E402
from app.providers.contracts import (  # noqa: E402
    ExtractionResult,
    ParsedDocument,
    ProviderError,
)


class PrivateExternalPackTests(unittest.TestCase):
    def test_maps_single_explicit_gst_to_tax(self) -> None:
        fields = _expected_fields(
            {
                "SELLER_NAME": {"text": "Acme Logistics"},
                "NUMBER": {"text": "INVOICE # INV-001"},
                "DATE": {"text": "Date: 18-Jun-2026"},
                "DUE_DATE": {"text": "Due Date : 18-Jul-2026"},
                "SUB_TOTAL": {"text": "SUB_TOTAL : 100.00 USD"},
                "GST(9%)": {"text": "GST(9%) : 9.00"},
                "TOTAL": {"text": "TOTAL : 109.00 USD"},
            }
        )

        self.assertEqual(fields["invoice_number"], "INV-001")
        self.assertEqual(fields["tax"], "9.00")
        self.assertEqual(fields["currency"], "USD")

    def test_does_not_choose_from_multiple_gst_rate_options(self) -> None:
        fields = _expected_fields(
            {
                "SUB_TOTAL": {"text": "SUB_TOTAL : 100.00 EUR"},
                "GST(5%)": {"text": "GST(5%) : 5.00"},
                "GST(9%)": {"text": "GST(9%) : 9.00"},
                "TOTAL": {"text": "TOTAL : 109.00 EUR"},
            }
        )

        self.assertIsNone(fields["tax"])

    def test_successful_retry_clears_previous_provider_error(self) -> None:
        class Parser:
            provider_name = "test_parser"

            def parse(self, _source):
                return ParsedDocument(text="FROM\nAcme Logistics\nTOTAL : 10.00 USD")

        class Extractor:
            provider_name = "test_extractor"

            def __init__(self) -> None:
                self.calls = 0

            def extract_invoice(self, _parsed):
                self.calls += 1
                if self.calls == 1:
                    raise ProviderError("rate_limited", self.provider_name, retryable=True)
                return ExtractionResult(
                    extraction=InvoiceExtraction(
                        data=InvoiceData(
                            vendor_name="Acme Logistics",
                            invoice_number="INV-001",
                            total=Decimal("10.00"),
                            currency="USD",
                        )
                    ),
                    provider_name=self.provider_name,
                )

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "invoice.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            observation = _run_document(
                "doc-1",
                source,
                Parser(),
                Extractor(),
                max_attempts=2,
                retry_backoff_seconds=0,
            )

        self.assertIsNone(observation["error"])
        self.assertEqual(observation["predicted_fields"]["total"], "10.00")

    def test_holdout_cannot_reuse_cached_diagnostic_observations(self) -> None:
        with self.assertRaisesRegex(SystemExit, "cannot reuse cached"):
            _load_cached_observations(Path("ignored.json"), "holdout")


if __name__ == "__main__":
    unittest.main()
