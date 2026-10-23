from __future__ import annotations

import unittest

from scripts.quality_report import complexity_violations, function_length_violations


class QualityGateTests(unittest.TestCase):
    def test_new_complex_function_fails_the_complexity_budget(self) -> None:
        report = {
            "backend/app/new_service.py": [
                {
                    "type": "function",
                    "name": "new_workflow",
                    "complexity": 16,
                }
            ]
        }

        violations = complexity_violations(report)

        self.assertEqual(len(violations), 1)
        self.assertIn("no exception is recorded", violations[0])

    def test_existing_exception_cannot_exceed_its_recorded_score(self) -> None:
        report = {
            "backend/app/system/dashboard.py": [
                {
                    "type": "method",
                    "classname": "SystemDashboardService",
                    "name": "_flow",
                    "complexity": 17,
                }
            ]
        }

        violations = complexity_violations(report)

        self.assertEqual(len(violations), 1)
        self.assertIn("increased from allowed 16 to 17", violations[0])

    def test_new_long_function_fails_the_length_budget(self) -> None:
        report = {
            "backend/app/new_service.py": [
                {
                    "type": "function",
                    "name": "new_workflow",
                    "complexity": 3,
                    "lineno": 10,
                    "endline": 90,
                }
            ]
        }

        violations = function_length_violations(report)

        self.assertEqual(len(violations), 1)
        self.assertIn("81 lines; no exception is recorded", violations[0])

    def test_existing_long_function_cannot_grow(self) -> None:
        report = {
            "backend/app/main.py": [
                {
                    "type": "function",
                    "name": "create_app",
                    "complexity": 6,
                    "lineno": 1,
                    "endline": 100,
                }
            ]
        }

        violations = function_length_violations(report)

        self.assertEqual(len(violations), 1)
        self.assertIn("increased from allowed 99 to 100 lines", violations[0])

    def test_test_functions_do_not_consume_production_budgets(self) -> None:
        report = {
            "backend/app/tests/test_large_fixture.py": [
                {
                    "type": "function",
                    "name": "test_fixture",
                    "complexity": 30,
                    "lineno": 1,
                    "endline": 200,
                }
            ]
        }

        self.assertEqual(complexity_violations(report), [])
        self.assertEqual(function_length_violations(report), [])


if __name__ == "__main__":
    unittest.main()
