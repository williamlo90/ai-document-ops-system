from __future__ import annotations

import unittest

from app.evaluation.provider_costs import build_provider_economics


class ProviderEconomicsTests(unittest.TestCase):
    def test_aggregates_reported_usage_and_list_price_cost(self) -> None:
        observations = [
            {
                "provider_attempts": [
                    {
                        "stage": "parser",
                        "status": "succeeded",
                        "usage": {
                            "pages_processed": 1,
                            "document_size_bytes": 4096,
                        },
                    },
                    {
                        "stage": "extractor",
                        "status": "succeeded",
                        "usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 200,
                            "output_tokens": 500,
                            "total_tokens": 1500,
                        },
                    },
                    {
                        "stage": "extractor",
                        "status": "failed",
                        "error": "extractor_http_error",
                    },
                ]
            }
        ]

        result = build_provider_economics(
            observations,
            parser_model="mistral-ocr-4-0",
            extractor_model="gpt-5.4-mini-2026-03-17",
        )

        self.assertEqual(result["usage"]["ocr_pages_processed"], 1)
        self.assertEqual(result["usage"]["extractor_input_tokens"], 1000)
        self.assertEqual(result["attempts"]["failure_codes"], {"extractor_http_error": 1})
        self.assertEqual(result["cost"]["status"], "estimated_from_provider_reported_usage")
        self.assertEqual(result["cost"]["estimated_total_usd"], 0.006865)

    def test_unknown_model_does_not_invent_a_cost(self) -> None:
        result = build_provider_economics(
            [],
            parser_model="unknown-ocr",
            extractor_model="unknown-extractor",
        )

        self.assertEqual(result["cost"]["status"], "unavailable_unknown_pricing")
        self.assertIsNone(result["cost"]["estimated_total_usd"])


if __name__ == "__main__":
    unittest.main()
