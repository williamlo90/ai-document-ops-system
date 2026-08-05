import unittest

from app.benchmark.datasets import scenarios
from app.benchmark.service import run_benchmark
from app.providers.mock import MockInvoiceExtractor


class BenchmarkServiceTests(unittest.TestCase):
    def test_mock_benchmark_is_repeatable(self) -> None:
        first = run_benchmark(MockInvoiceExtractor(), scenarios())
        second = run_benchmark(MockInvoiceExtractor(), scenarios())
        self.assertEqual(first, second)
