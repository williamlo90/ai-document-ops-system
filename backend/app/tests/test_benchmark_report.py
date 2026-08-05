import unittest

from app.benchmark.metrics import BenchmarkMetrics
from app.benchmark.report import report


class BenchmarkReportTests(unittest.TestCase):
    def test_report_names_dataset_version(self) -> None:
        self.assertEqual(report(BenchmarkMetrics(1, 1.0, 1.0))["dataset_version"], "invoice-scenarios-v1")
