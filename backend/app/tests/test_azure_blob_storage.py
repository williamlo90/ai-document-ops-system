from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from azure.storage.blob import BlobServiceClient
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.core.security import SecurityContext
from app.documents.repositories import (
    InMemoryAuditRepository,
    InMemoryDocumentRepository,
    InMemoryJobRepository,
)
from app.documents.services import DocumentUploadService
from app.documents.workflow import DocumentWorkflowService
from app.main import create_app
from app.providers.azure_blob_storage import AzureBlobStorageService
from app.providers.storage import StorageError, StorageNotFoundError
from app.tests.auth_helpers import session_headers


@unittest.skipUnless(
    os.getenv("AZURITE_TEST_CONNECTION_STRING"),
    "AZURITE_TEST_CONNECTION_STRING is required for Azure Blob integration tests",
)
class AzureBlobStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection_string = os.environ["AZURITE_TEST_CONNECTION_STRING"]
        self.container_name = f"documents-{uuid4().hex[:16]}"
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = AzureBlobStorageService(
            container=self.container_name,
            cache_root=Path(self.temp_dir.name),
            max_upload_bytes=1_000,
            connection_string=self.connection_string,
            create_container=True,
        )

    def tearDown(self) -> None:
        service = _blob_service(self.connection_string)
        service.delete_container(self.container_name)
        self.temp_dir.cleanup()

    def test_private_upload_download_metadata_duplicate_and_delete(self) -> None:
        content = b"%PDF- azure contract"
        first = self.storage.save_upload(
            "invoice.pdf", "application/pdf", content, workspace_id="acme"
        )
        second = self.storage.save_upload(
            "invoice.pdf", "application/pdf", content, workspace_id="acme"
        )

        self.assertNotEqual(first.storage_key, second.storage_key)
        self.assertEqual(self.storage.open_for_parser(first.storage_key).read_bytes(), content)
        properties = self.storage.container.get_blob_client(first.storage_key).get_blob_properties()
        self.assertIsNone(self.storage.container.get_container_properties().public_access)
        self.assertEqual(properties.content_settings.content_type, "application/pdf")
        self.assertEqual(properties.metadata["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(properties.metadata["size_bytes"], str(len(content)))
        self.assertEqual(len(properties.metadata["workspace_hash"]), 24)
        self.assertIsNone(self.storage.create_download_url(first.storage_key))

        self.storage.delete(first.storage_key)
        self.storage.delete(first.storage_key)
        with self.assertRaises(StorageNotFoundError):
            self.storage.open_for_parser(first.storage_key)

    def test_rejects_invalid_blob_key_and_oversized_content(self) -> None:
        with self.assertRaises(StorageError):
            self.storage.open_for_parser("../other-workspace/invoice.pdf")
        with self.assertRaises(StorageError):
            self.storage.save_upload("invoice.pdf", "application/pdf", b"%PDF-" + b"x" * 1_000)

    def test_metadata_failure_rolls_back_uploaded_blob(self) -> None:
        class FailingDocuments(InMemoryDocumentRepository):
            def add(self, document):
                raise RuntimeError("metadata write failed")

        service = DocumentUploadService(
            storage=self.storage,
            documents=FailingDocuments(),
            jobs=InMemoryJobRepository(),
            audits=InMemoryAuditRepository(),
            workflow=DocumentWorkflowService(),
        )
        with self.assertRaisesRegex(RuntimeError, "metadata write failed"):
            service.upload_pdf(
                "invoice.pdf",
                "application/pdf",
                [b"%PDF- rollback"],
                context=SecurityContext(actor="Acme Admin", is_admin=True, workspace_id="acme"),
            )
        self.assertEqual(list(self.storage.container.list_blobs()), [])

    def test_document_flow_is_tenant_isolated_and_retention_removes_blob(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token=None,
            upload_root=Path(self.temp_dir.name) / "app-cache",
            max_upload_bytes=1_000,
            document_storage_backend="azure-blob",
            azure_storage_connection_string=self.connection_string,
            azure_storage_container=self.container_name,
            azure_storage_create_container=False,
            malware_scanning_enabled=True,
            malware_scanner_backend="signature",
        )
        with TestClient(create_app(settings)) as client:
            acme = session_headers(client, actor="Acme Admin", workspace_id="acme")
            other = session_headers(client, actor="Other Admin", workspace_id="other")
            upload = client.post(
                "/documents/upload",
                headers=acme,
                files={"file": ("invoice.pdf", b"%PDF- invoice", "application/pdf")},
            )
            self.assertEqual(upload.status_code, 200)
            document_id = upload.json()["document"]["id"]
            storage_key = client.app.state.container.documents.get(UUID(document_id)).storage_key

            self.assertEqual(
                client.get(f"/documents/{document_id}/content", headers=other).status_code,
                404,
            )
            self.assertEqual(
                client.get(f"/documents/{document_id}/content", headers=acme).status_code,
                200,
            )
            self.assertEqual(
                client.post(f"/documents/{document_id}/process", headers=acme).status_code,
                200,
            )
            self.assertEqual(
                client.post(f"/review/{document_id}/approve", headers=acme).status_code,
                200,
            )
            removed = client.request(
                "DELETE",
                f"/documents/{document_id}",
                headers=acme,
                json={"reason": "azure_blob_retention_test"},
            )
            self.assertEqual(removed.status_code, 200)
            with self.assertRaises(StorageNotFoundError):
                self.storage.open_for_parser(storage_key)


def _blob_service(connection_string: str) -> BlobServiceClient:
    from app.providers.azure_blob_storage import _AZURITE_CONNECTION_STRING

    return BlobServiceClient.from_connection_string(
        _AZURITE_CONNECTION_STRING
        if connection_string == "UseDevelopmentStorage=true"
        else connection_string
    )
