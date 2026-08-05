from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOTS = (ROOT / "documents", ROOT / "extraction", ROOT / "validation")
FORBIDDEN_PREFIXES = ("app.api", "app.storage", "app.bootstrap", "app.integrations")


class ModuleBoundaryTests(unittest.TestCase):
    def test_domain_modules_do_not_import_delivery_or_infrastructure(self) -> None:
        violations: list[str] = []
        for domain_root in DOMAIN_ROOTS:
            for path in domain_root.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imports = [
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                ]
                for imported in imports:
                    if imported.startswith(FORBIDDEN_PREFIXES):
                        violations.append(f"{path.name}: {imported}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
