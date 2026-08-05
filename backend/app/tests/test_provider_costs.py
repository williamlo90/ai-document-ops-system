import unittest
from decimal import Decimal

from app.evaluation.provider_costs import estimate_cost


class ProviderCostTests(unittest.TestCase):
    def test_cost_is_deterministic_decimal(self) -> None:
        self.assertEqual(estimate_cost(10, 5, input_rate=Decimal("0.001"), output_rate=Decimal("0.002")), Decimal("0.020000"))
