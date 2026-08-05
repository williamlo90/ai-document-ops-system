import unittest

from app.benchmark.metrics import BenchmarkMetrics


class BenchmarkMetricTests(unittest.TestCase):
    def test_metrics_keep_separate_dimensions(self) -> None:
        metrics = BenchmarkMetrics(3, 0.9, 1.0)
        self.assertNotEqual(metrics.mean_field_match, metrics.validation_accuracy)
