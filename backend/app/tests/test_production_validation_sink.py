from __future__ import annotations

import unittest

from app.production_validation_sink import (
    InMemoryDraftStore,
    build_draft,
    validate_sink_environment,
)


class ProductionValidationSinkTests(unittest.TestCase):
    def test_persists_one_draft_per_delivery_key(self) -> None:
        payload = {
            "custom_invoice_review_delivery_key": "delivery-key-123",
            "items": [{"qty": 2, "rate": 50}],
            "taxes": [{"rate": 10}],
        }
        key, first = build_draft(payload)
        _, second = build_draft({**payload, "bill_no": "changed"})
        store = InMemoryDraftStore()

        stored_first = store.create_or_get(key, first)
        stored_second = store.create_or_get(key, second)

        self.assertEqual(stored_first["name"], stored_second["name"])
        self.assertNotIn("bill_no", stored_second)
        self.assertEqual(stored_first["grand_total"], "110.00")

    def test_requires_explicit_production_validation_guards(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_sink_environment(
                {
                    "APP_ENV": "local",
                    "VALIDATION_SINK_ENABLED": "false",
                    "PRODUCTION_VALIDATION_RUN_ID": "short",
                    "VALIDATION_SINK_SECRET": "weak",
                }
            )

        config = validate_sink_environment(
            {
                "APP_ENV": "production",
                "VALIDATION_SINK_ENABLED": "true",
                "PRODUCTION_VALIDATION_RUN_ID": "pg01-20261002t120000z-abcd1234",
                "VALIDATION_SINK_SECRET": "s" * 32,
                "VALIDATION_SINK_RESPONSE_DELAY_SECONDS": "5",
            }
        )
        self.assertEqual(config.response_delay_seconds, 5)
        self.assertTrue(config.authorization.startswith("token validation:"))

    def test_rejects_malformed_invoice_lines(self) -> None:
        with self.assertRaises(ValueError):
            build_draft(
                {
                    "custom_invoice_review_delivery_key": "delivery-key-123",
                    "items": "not-an-array",
                }
            )

        with self.assertRaises(ValueError):
            build_draft(
                {
                    "custom_invoice_review_delivery_key": "delivery-key-123",
                    "items": [{"qty": "not-a-number", "rate": 50}],
                }
            )


if __name__ == "__main__":
    unittest.main()
