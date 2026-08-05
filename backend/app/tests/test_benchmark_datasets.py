import unittest

from app.benchmark.datasets import DATASET_VERSION, scenarios


class BenchmarkDatasetTests(unittest.TestCase):
    def test_dataset_is_versioned_and_scenario_ids_are_unique(self) -> None:
        cases = scenarios()
        self.assertEqual(DATASET_VERSION, "invoice-scenarios-v1")
        self.assertEqual(len({case.scenario_id for case in cases}), len(cases))
