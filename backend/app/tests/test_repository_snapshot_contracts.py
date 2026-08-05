from __future__ import annotations

import unittest

from app.documents.models import DocumentRecord
from app.documents.repositories import DuplicateInvoiceIdentity, InMemoryDocumentRepository
from app.documents.status import DocumentStatus


class RepositorySnapshotContractsTests(unittest.TestCase):
    def test_read_returns_isolated_snapshot_and_save_is_explicit(self) -> None:
        repository = InMemoryDocumentRepository()
        document = DocumentRecord("invoice.pdf", "key", "application/pdf")
        repository.add(document)
        loaded = repository.get(document.id)
        assert loaded is not None
        loaded.status = DocumentStatus.QUEUED
        self.assertEqual(repository.get(document.id).status, DocumentStatus.UPLOADED)  # type: ignore[union-attr]
        repository.save(loaded)
        self.assertEqual(repository.get(document.id).status, DocumentStatus.QUEUED)  # type: ignore[union-attr]

    def test_duplicate_identity_is_workspace_scoped(self) -> None:
        repository = InMemoryDocumentRepository()
        repository.reserve_identity("alpha", "Acme", "INV-1")
        repository.reserve_identity("beta", "Acme", "INV-1")
        with self.assertRaises(DuplicateInvoiceIdentity):
            repository.reserve_identity("alpha", "acme", "inv-1")


if __name__ == "__main__":
    unittest.main()
