from __future__ import annotations

import unittest

from app.documents.models import DocumentRecord
from app.documents.repositories import InMemoryDocumentRepository
from app.invoices.queries import InvoiceQueries


class InvoiceQueryContractTests(unittest.TestCase):
    def test_query_is_workspace_scoped_and_returns_read_model(self) -> None:
        repository = InMemoryDocumentRepository()
        repository.add(DocumentRecord("alpha.pdf", "a", "application/pdf", workspace_id="alpha"))
        repository.add(DocumentRecord("beta.pdf", "b", "application/pdf", workspace_id="beta"))
        rows = InvoiceQueries(repository).list_for_workspace("alpha")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["filename"], "alpha.pdf")


if __name__ == "__main__":
    unittest.main()
