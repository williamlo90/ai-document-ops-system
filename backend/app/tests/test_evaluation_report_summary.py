from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.evaluation.report_summary import load_latest_provider_cost_summary


class EvaluationReportSummaryTests(unittest.TestCase):
    def test_returns_honest_empty_state_without_a_sealed_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = load_latest_provider_cost_summary(Path(temp_dir))

        self.assertFalse(summary["available"])
        self.assertIn("No sealed external evaluation", str(summary["message"]))

    def test_summarizes_latest_sealed_holdout_provider_costs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir)
            self._write_report(evidence_dir / "external-invoice-v1-holdout-final.json", 1.0)
            self._write_report(evidence_dir / "external-invoice-v2-holdout-final.json", 0.063624)

            summary = load_latest_provider_cost_summary(evidence_dir)

        self.assertTrue(summary["available"])
        self.assertEqual(summary["documents_count"], 10)
        self.assertEqual(summary["estimated_total_usd"], 0.063624)
        self.assertEqual(summary["estimated_per_document_usd"], 0.006362)
        self.assertEqual(summary["ocr"]["estimated_cost_usd"], 0.04)
        self.assertEqual(summary["extraction"]["estimated_cost_usd"], 0.023624)
        self.assertEqual(summary["extraction"]["total_tokens"], 11309)

    def _write_report(self, path: Path, total_cost: float) -> None:
        path.write_text(
            json.dumps(
                {
                    "dataset_class": "external licensed synthetic invoices",
                    "split": "holdout",
                    "documents_count": 10,
                    "generated_at": "2026-07-20T04:32:41Z"
                    if total_cost < 1
                    else "2026-07-19T04:32:41Z",
                    "holdout_seal_verified": True,
                    "provider_economics": {
                        "usage": {
                            "ocr_pages_processed": 10,
                            "extractor_input_tokens": 7271,
                            "extractor_cached_input_tokens": 0,
                            "extractor_output_tokens": 4038,
                            "extractor_total_tokens": 11309,
                        },
                        "attempts": {"total": 20, "succeeded": 20, "failed": 0},
                        "cost": {
                            "status": "estimated_from_provider_reported_usage",
                            "parser_model": "mistral-ocr-latest",
                            "extractor_model": "gpt-5.4-mini-2026-03-17",
                            "ocr_usd": 0.04,
                            "extractor_input_usd": 0.005453,
                            "extractor_cached_input_usd": 0.0,
                            "extractor_output_usd": 0.018171,
                            "estimated_total_usd": total_cost,
                            "claim_boundary": "List-price estimate only.",
                        },
                        "pricing_snapshot": {
                            "effective_date": "2026-07-20",
                            "currency": "USD",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
