from __future__ import annotations

import unittest
from pathlib import Path

from app.benchmark.guardrails import (
    BenchmarkRunBlocked,
    provider_mode,
    safety_info,
    validate_benchmark_run,
)
from app.benchmark.models import EvaluationDataset, EvaluationDocument
from app.benchmark.providers import MISTRAL_LLM_PROVIDER_PAIR, MOCK_PROVIDER_PAIR
from app.core.settings import Settings


class BenchmarkGuardrailTests(unittest.TestCase):
    def test_mock_provider_is_not_limited(self) -> None:
        dataset = _dataset(10)
        settings = _settings(max_documents=1)

        validate_benchmark_run(dataset, MOCK_PROVIDER_PAIR, settings)

        self.assertEqual(provider_mode(MOCK_PROVIDER_PAIR), "mock")
        self.assertIn("does not call paid", safety_info(MOCK_PROVIDER_PAIR, settings).message)

    def test_real_provider_blocks_dataset_above_limit(self) -> None:
        dataset = _dataset(2)
        settings = _settings(max_documents=1)

        with self.assertRaisesRegex(BenchmarkRunBlocked, "limit is 1"):
            validate_benchmark_run(dataset, MISTRAL_LLM_PROVIDER_PAIR, settings)

    def test_real_provider_allows_dataset_at_limit(self) -> None:
        dataset = _dataset(2)
        settings = _settings(max_documents=2)

        validate_benchmark_run(dataset, MISTRAL_LLM_PROVIDER_PAIR, settings)

        info = safety_info(MISTRAL_LLM_PROVIDER_PAIR, settings)
        self.assertEqual(info.provider_mode, "real")
        self.assertEqual(info.max_documents, 2)


def _dataset(count: int) -> EvaluationDataset:
    return EvaluationDataset(
        name="unit",
        documents=tuple(
            EvaluationDocument(
                document_id=f"doc-{index}",
                expected_fields={"total": "10.00"},
            )
            for index in range(count)
        ),
    )


def _settings(max_documents: int) -> Settings:
    return Settings(
        app_env="test",
        admin_token="token",
        upload_root=Path("uploads"),
        max_upload_bytes=1000,
        benchmark_real_provider_max_documents=max_documents,
    )


if __name__ == "__main__":
    unittest.main()
