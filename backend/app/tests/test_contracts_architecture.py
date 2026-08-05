from __future__ import annotations

import ast
import unittest
from pathlib import Path

from app.contracts import (
    AuditRepositoryPort,
    CorrectionRepositoryPort,
    DocumentRepositoryPort,
    ProcessingJobRepositoryPort,
    ReviewRepositoryPort,
    TransactionManagerPort,
)
from app.documents.repositories import (
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryJobRepository,
    InMemoryTransactionManager,
)
from app.review.repositories import InMemoryCorrectionRepository, InMemoryReviewRepository


class ContractArchitectureTests(unittest.TestCase):
    def test_current_in_memory_adapters_satisfy_repository_ports(self) -> None:
        documents = InMemoryDocumentRepository()
        audits = InMemoryAuditRepository()
        jobs = InMemoryJobRepository()

        self.assertIsInstance(documents, DocumentRepositoryPort)
        self.assertIsInstance(audits, AuditRepositoryPort)
        self.assertIsInstance(jobs, ProcessingJobRepositoryPort)
        self.assertIsInstance(InMemoryTransactionManager(documents, audits, jobs), TransactionManagerPort)
        self.assertIsInstance(InMemoryReviewRepository(), ReviewRepositoryPort)
        self.assertIsInstance(InMemoryCorrectionRepository(), CorrectionRepositoryPort)

    def test_contracts_do_not_depend_on_infrastructure_or_delivery_layers(self) -> None:
        contracts_dir = Path(__file__).parents[1] / "contracts"
        forbidden_parts = {"api", "bootstrap", "repositories", "services", "sqlite_repositories"}

        violations: list[str] = []
        for path in contracts_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    if forbidden_parts.intersection(module.split(".")):
                        violations.append(f"{path.name}: {module}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
