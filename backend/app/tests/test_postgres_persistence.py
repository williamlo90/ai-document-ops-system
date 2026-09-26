from __future__ import annotations

import os
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.documents.jobs import ProcessingJob
from app.documents.models import DocumentRecord
from app.documents.sqlite_repositories import SqliteDocumentRepository
from app.invoices.queries import InvoiceListQuery
from app.postgres.queries import PostgresInvoiceQueryRepository
from app.postgres.repositories import PostgresJobRepository
from app.postgres.store import PostgresStore, _postgres_sql
from app.main import create_app


class PostgresSqlCompatibilityTests(unittest.TestCase):
    def test_translates_placeholders_and_insert_or_ignore(self) -> None:
        sql = _postgres_sql(
            "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)"
        )
        self.assertIn("VALUES (%s, %s)", sql)
        self.assertTrue(sql.endswith("ON CONFLICT DO NOTHING"))

    def test_translates_replace_to_explicit_upsert(self) -> None:
        sql = _postgres_sql(
            "INSERT OR REPLACE INTO notifications (id, workspace_id, payload) VALUES (?, ?, ?)"
        )
        self.assertIn("ON CONFLICT (id) DO UPDATE SET", sql)
        self.assertIn("payload = EXCLUDED.payload", sql)


@unittest.skipUnless(
    os.getenv("POSTGRES_TEST_DATABASE_URL"),
    "POSTGRES_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgresPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        database_url = os.environ["POSTGRES_TEST_DATABASE_URL"]
        self.primary = PostgresStore(database_url, pool_size=2)
        self.secondary = PostgresStore(database_url, pool_size=2)
        self.documents = SqliteDocumentRepository(self.primary)  # compatible SQL adapter
        self.jobs = PostgresJobRepository(self.primary)
        self.created_document_ids: list[str] = []

    def tearDown(self) -> None:
        for document_id in self.created_document_ids:
            self.primary.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        self.primary.close()
        self.secondary.close()

    def _document(self) -> DocumentRecord:
        document = DocumentRecord(
            original_filename="postgres-contract.pdf",
            storage_key="postgres-contract",
            content_type="application/pdf",
            workspace_id="postgres-contract",
        )
        self.documents.add(document)
        self.created_document_ids.append(str(document.id))
        return document

    def test_document_and_invoice_read_contract(self) -> None:
        document = self._document()
        loaded = self.documents.get(document.id)
        self.assertEqual(loaded.original_filename, document.original_filename)
        page = PostgresInvoiceQueryRepository(self.primary).list(
            InvoiceListQuery(workspace_id="postgres-contract")
        )
        self.assertEqual(page.total, 1)
        self.assertEqual(page.documents[0].id, document.id)

    def test_transaction_rolls_back(self) -> None:
        document = self._document()
        with self.assertRaises(RuntimeError):
            with self.primary.transaction():
                self.primary.execute(
                    "UPDATE documents SET original_filename = ? WHERE id = ?",
                    ("rolled-back.pdf", str(document.id)),
                )
                raise RuntimeError("rollback")
        self.assertEqual(
            self.documents.get(document.id).original_filename, document.original_filename
        )

    def test_two_workers_cannot_claim_the_same_job(self) -> None:
        document = self._document()
        job = ProcessingJob(document_id=document.id)
        self.jobs.add(job)
        barrier = threading.Barrier(2)

        def claim(repository: PostgresJobRepository) -> str | None:
            barrier.wait()
            claimed = repository.claim_next_processable()
            return str(claimed.id) if claimed else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    claim,
                    (self.jobs, PostgresJobRepository(self.secondary)),
                )
            )
        self.assertEqual(results.count(str(job.id)), 1)
        self.assertEqual(results.count(None), 1)

    def test_two_queue_workers_cannot_claim_the_same_job_id(self) -> None:
        document = self._document()
        job = self.jobs.add(ProcessingJob(document_id=document.id))
        barrier = threading.Barrier(2)

        def claim(repository: PostgresJobRepository) -> str | None:
            barrier.wait()
            claimed = repository.claim_processable(job.id)
            return claimed.lease_token if claimed else None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    claim,
                    (self.jobs, PostgresJobRepository(self.secondary)),
                )
            )
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_api_and_worker_path_share_postgres_state(self) -> None:
        workspace = "postgres-api-contract"
        with tempfile.TemporaryDirectory() as upload_root:
            settings = Settings(
                app_env="test",
                admin_token="postgres-test-token",
                upload_root=Path(upload_root),
                max_upload_bytes=1000,
                workspace_id=workspace,
                storage_backend="postgres",
                database_url=os.environ["POSTGRES_TEST_DATABASE_URL"],
                database_pool_size=3,
            )
            with TestClient(create_app(settings)) as client:
                headers = {"X-Admin-Token": "postgres-test-token"}
                upload = client.post(
                    "/documents/upload",
                    headers=headers,
                    files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
                )
                self.assertEqual(upload.status_code, 200)
                document_id = upload.json()["document"]["id"]
                self.created_document_ids.append(document_id)
                process = client.post(f"/documents/{document_id}/process", headers=headers)
                self.assertEqual(process.status_code, 200)
                detail = client.get(f"/documents/{document_id}", headers=headers)
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["document"]["status"], "needs_review")
