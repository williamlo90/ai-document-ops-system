from __future__ import annotations

import unittest

from app.benchmark.pricing import get_cost_estimate


class PricingTests(unittest.TestCase):
    def test_known_provider_returns_cost_keys(self) -> None:
        result = get_cost_estimate("mock", 2, 1000.0)
        self.assertIn("estimated_cost_per_document", result)
        self.assertIn("estimated_cost_total", result)
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["document_count"], 2)

    def test_mock_provider_returns_zero_cost(self) -> None:
        result = get_cost_estimate("mock", 1, 0.0)
        self.assertEqual(result["estimated_cost_total"], 0.0)

    def test_mock_provider_pair_returns_zero_cost(self) -> None:
        result = get_cost_estimate("mock_parser+mock_extractor", 1, 100.0)
        self.assertEqual(result["estimated_cost_total"], 0.0)

    def test_unknown_provider_returns_note(self) -> None:
        result = get_cost_estimate("unknown_provider", 1, 0.0)
        self.assertIsNone(result["estimated_cost_per_document"])
        self.assertIn("note", result)

    def test_multiple_documents_scales_cost(self) -> None:
        single = get_cost_estimate("mistral_ocr+llm_json", 1, 0.0)
        double = get_cost_estimate("mistral_ocr+llm_json", 2, 0.0)
        self.assertGreater(double["estimated_cost_total"], single["estimated_cost_total"])

    def test_latency_increases_cost(self) -> None:
        fast = get_cost_estimate("mistral_ocr+llm_json", 1, 0.0)
        slow = get_cost_estimate("mistral_ocr+llm_json", 1, 5000.0)
        self.assertGreater(slow["estimated_cost_total"], fast["estimated_cost_total"])

    def test_non_negative_values(self) -> None:
        result = get_cost_estimate("mock", 5, 3000.0)
        self.assertGreaterEqual(result["estimated_cost_per_document"], 0.0)
        self.assertGreaterEqual(result["estimated_cost_total"], 0.0)


if __name__ == "__main__":
    unittest.main()
