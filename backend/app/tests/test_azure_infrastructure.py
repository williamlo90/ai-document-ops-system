from __future__ import annotations

import unittest

from scripts.validate_azure_iac import validate_sources


class AzureInfrastructureTests(unittest.TestCase):
    def test_source_contracts_are_safe_and_complete(self) -> None:
        self.assertEqual(validate_sources(), [])


if __name__ == "__main__":
    unittest.main()
