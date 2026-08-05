from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentops.repositories import (
    InMemoryScenarioEvaluationRepository,
    ScenarioEvaluationRecord,
)
from app.documents.models import DocumentRecord
from app.documents.repositories import (
    DocumentRepository,
    InMemoryDocumentRepository,
)
from app.documents.sqlite_repositories import (
    SqliteAuditRepository,
    SqliteDocumentRepository,
    SqliteStore,
)
from app.documents.state_writer import DocumentStateWriter
from app.documents.status import DocumentStatus
from app.documents.workflow import DocumentWorkflowService
from app.operations.notifications import InMemoryNotificationRepository, Notification


class RepositorySnapshotContractTests(unittest.TestCase):
    def test_document_repository_requires_explicit_save_in_memory_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SqliteStore(Path(temp_dir) / "repository-contract.sqlite3")
            try:
                repositories: tuple[DocumentRepository, ...] = (
                    InMemoryDocumentRepository(),
                    SqliteDocumentRepository(store),
                )
                for repository in repositories:
                    with self.subTest(repository=type(repository).__name__):
                        self._assert_document_snapshot_contract(repository)
            finally:
                store.close()

    def test_nested_evaluation_evidence_is_isolated(self) -> None:
        repository = InMemoryScenarioEvaluationRepository()
        evidence = {"fields": {"vendor": "Acme"}}
        record = ScenarioEvaluationRecord(
            workspace_id="default",
            evaluation_type="invoice",
            dataset_id="dataset",
            dataset_version="1",
            scenario_id="scenario-1",
            target_id="document-1",
            passed=True,
            evidence=evidence,
        )

        repository.add(record)
        evidence["fields"]["vendor"] = "Mutated"
        fetched = repository.list_recent("default")[0]
        fetched.evidence["fields"]["vendor"] = "Changed again"

        self.assertEqual(
            repository.list_recent("default")[0].evidence,
            {"fields": {"vendor": "Acme"}},
        )

    def test_notification_changes_require_save(self) -> None:
        repository = InMemoryNotificationRepository()
        notification = repository.add(
            Notification(
                workspace_id="default",
                source_key="invoice:1",
                notification_type="review",
                title="Review invoice",
                message="An invoice needs review.",
            )
        )

        notification.mark_read()
        self.assertIsNone(repository.get(notification.id).read_at)

        repository.save(notification)
        self.assertIsNotNone(repository.get(notification.id).read_at)

    def test_state_writer_rolls_back_audit_when_document_save_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SqliteStore(Path(temp_dir) / "state-writer.sqlite3")
            documents = SqliteDocumentRepository(store)
            audits = SqliteAuditRepository(store)
            document = documents.add(
                DocumentRecord(
                    original_filename="invoice.pdf",
                    storage_key="invoice.pdf",
                    content_type="application/pdf",
                )
            )
            writer = DocumentStateWriter(
                documents,
                audits,
                DocumentWorkflowService(),
                store,
            )
            try:
                with (
                    patch.object(
                        documents,
                        "save",
                        side_effect=RuntimeError("injected persistence failure"),
                    ),
                    self.assertRaisesRegex(RuntimeError, "injected persistence failure"),
                ):
                    writer.transition(
                        document,
                        DocumentStatus.QUEUED,
                        actor="tester",
                    )

                self.assertEqual(documents.get(document.id).status, DocumentStatus.UPLOADED)
                self.assertEqual(audits.list_for_document(document.id), [])
            finally:
                store.close()

    def _assert_document_snapshot_contract(self, repository: DocumentRepository) -> None:
        created = repository.add(
            DocumentRecord(
                original_filename="invoice.pdf",
                storage_key="invoice.pdf",
                content_type="application/pdf",
            )
        )

        fetched = repository.get(created.id)
        fetched.status = DocumentStatus.QUEUED
        self.assertEqual(repository.get(created.id).status, DocumentStatus.UPLOADED)

        repository.save(fetched)
        self.assertEqual(repository.get(created.id).status, DocumentStatus.QUEUED)

        listed = repository.list_by_workspace("default")
        listed[0].status = DocumentStatus.FAILED
        self.assertEqual(repository.get(created.id).status, DocumentStatus.QUEUED)
