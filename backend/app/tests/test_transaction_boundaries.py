from __future__ import annotations

import unittest

from app.documents.models import AuditEvent, DocumentRecord
from app.documents.repositories import InMemoryAuditRepository, InMemoryDocumentRepository, InMemoryTransactionManager
from app.documents.state_writer import DocumentStateWriter
from app.documents.status import DocumentStatus


class FailingAuditRepository(InMemoryAuditRepository):
    def append(self, event: AuditEvent) -> None:
        raise RuntimeError("audit write failed")


class TransactionBoundaryTests(unittest.TestCase):
    def test_state_and_audit_commit_together(self) -> None:
        documents = InMemoryDocumentRepository()
        audits = InMemoryAuditRepository()
        transactions = InMemoryTransactionManager(documents, audits)
        original = DocumentRecord("invoice.pdf", "key", "application/pdf")
        documents.add(original)
        changed = documents.get(original.id)
        assert changed is not None
        changed.status = DocumentStatus.QUEUED
        event = AuditEvent(changed.id, "processing_queued", "operator", DocumentStatus.UPLOADED, DocumentStatus.QUEUED)
        DocumentStateWriter(documents, audits, transactions).save_with_audit(changed, event)
        self.assertEqual(documents.get(original.id).status, DocumentStatus.QUEUED)  # type: ignore[union-attr]
        self.assertEqual(audits.list_for_document(original.id), [event])

    def test_audit_failure_rolls_back_state(self) -> None:
        documents = InMemoryDocumentRepository()
        tracked_audits = InMemoryAuditRepository()
        transactions = InMemoryTransactionManager(documents, tracked_audits)
        original = DocumentRecord("invoice.pdf", "key", "application/pdf")
        documents.add(original)
        changed = documents.get(original.id)
        assert changed is not None
        changed.status = DocumentStatus.QUEUED
        event = AuditEvent(changed.id, "processing_queued", "operator")
        with self.assertRaises(RuntimeError):
            DocumentStateWriter(documents, FailingAuditRepository(), transactions).save_with_audit(changed, event)
        self.assertEqual(documents.get(original.id).status, DocumentStatus.UPLOADED)  # type: ignore[union-attr]
        self.assertEqual(tracked_audits.list_for_document(original.id), [])


if __name__ == "__main__":
    unittest.main()
