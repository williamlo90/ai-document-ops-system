from __future__ import annotations

import unittest

from app.exports.csv_security import escape_spreadsheet_formula


class CsvSecurityTests(unittest.TestCase):
    def test_escapes_spreadsheet_formula_prefixes(self) -> None:
        for value in ("=SUM(A1:A2)", "+1", "-1", "@cmd", " =cmd", "\t=cmd", "\n=cmd"):
            self.assertEqual(escape_spreadsheet_formula(value), "'" + value)

    def test_keeps_safe_strings_and_non_strings(self) -> None:
        self.assertEqual(escape_spreadsheet_formula("Acme"), "Acme")
        self.assertEqual(escape_spreadsheet_formula(123), 123)


if __name__ == "__main__":
    unittest.main()
