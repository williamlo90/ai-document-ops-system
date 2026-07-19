from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app
from app.integrations.models import IntegrationDeliveryRecord


class RetentionApiTests(unittest.TestCase):
    def test_admin_purge_removes_object_and_related_sqlite_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(_settings(root, storage_backend="sqlite"))
            with TestClient(app) as client:
                upload = client.post(
                    "/documents/upload",
                    headers={"X-Access-Token": "admin-token"},
                    files={"file": ("invoice.pdf", b"%PDF-invoice", "application/pdf")},
                )
                document_id = upload.json()["document"]["id"]
                storage_key = app.state.container.documents.get(UUID(document_id)).storage_key
                client.post(
                    f"/documents/{document_id}/cancel",
                    headers={"X-Access-Token": "admin-token"},
                    json={"reason": "test cleanup"},
                )
                app.state.container.integration_deliveries.reserve(
                    IntegrationDeliveryRecord(
                        workspace_id="default",
                        document_id=UUID(document_id),
                        adapter_name="mock-accounting",
                        idempotency_key="retention-export-key",
                        payload_hash="retention-test",
                    )
                )

                response = client.request(
                    "DELETE",
                    f"/documents/{document_id}",
                    json={"reason": "privacy_deletion_request"},
                    headers={"X-Access-Token": "admin-token"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertFalse((root / "uploads" / storage_key).exists())
                self.assertEqual(
                    client.get(
                        f"/documents/{document_id}",
                        headers={"X-Access-Token": "admin-token"},
                    ).status_code,
                    404,
                )
                store = app.state.container.documents.store
                self.assertEqual(
                    store.query_one(
                        "SELECT COUNT(*) AS count FROM audit_events WHERE document_id = ?",
                        (document_id,),
                    )["count"],
                    0,
                )
                self.assertEqual(
                    store.query_one(
                        "SELECT COUNT(*) AS count FROM integration_deliveries WHERE document_id = ?",
                        (document_id,),
                    )["count"],
                    0,
                )
                tombstone = store.query_one("SELECT document_fingerprint FROM data_purge_events")
                self.assertIsNotNone(tombstone)
                self.assertNotEqual(tombstone["document_fingerprint"], document_id)

    def test_retention_dry_run_is_admin_only_and_does_not_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_settings(Path(temp_dir), document_retention_days=1))
            with TestClient(app) as client:
                upload = client.post(
                    "/documents/upload",
                    headers={"X-Access-Token": "admin-token"},
                    files={"file": ("invoice.pdf", b"%PDF-invoice", "application/pdf")},
                )
                document_id = upload.json()["document"]["id"]
                document = app.state.container.documents.get(UUID(document_id))
                document.created_at = datetime.now(UTC) - timedelta(days=2)
                client.post(
                    f"/documents/{document_id}/cancel",
                    headers={"X-Access-Token": "admin-token"},
                    json={"reason": "test cleanup"},
                )

                forbidden = client.get(
                    "/operations/retention",
                    headers={"X-Access-Token": "reviewer-token"},
                )
                dry_run = client.post(
                    "/operations/retention/purge",
                    headers={"X-Access-Token": "admin-token"},
                    json={"dry_run": True, "reason": "retention_policy"},
                )

                self.assertEqual(forbidden.status_code, 403)
                self.assertEqual(dry_run.status_code, 200)
                self.assertTrue(dry_run.json()["dry_run"])
                self.assertIn(document_id, dry_run.json()["candidate_document_ids"])
                self.assertEqual(
                    client.get(
                        f"/documents/{document_id}",
                        headers={"X-Access-Token": "admin-token"},
                    ).status_code,
                    200,
                )

    def test_active_document_cannot_be_purged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with TestClient(create_app(_settings(Path(temp_dir)))) as client:
                upload = client.post(
                    "/documents/upload",
                    headers={"X-Access-Token": "admin-token"},
                    files={"file": ("invoice.pdf", b"%PDF-invoice", "application/pdf")},
                )
                document_id = upload.json()["document"]["id"]
                response = client.request(
                    "DELETE",
                    f"/documents/{document_id}",
                    json={"reason": "privacy_deletion_request"},
                    headers={"X-Access-Token": "admin-token"},
                )
                self.assertEqual(response.status_code, 409)

    def test_invalid_retention_window_is_rejected_at_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                create_app(_settings(Path(temp_dir), document_retention_days=0))


def _settings(root: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "local",
        "admin_token": "admin-token",
        "uploader_token": "uploader-token",
        "reviewer_token": "reviewer-token",
        "workspace_id": "default",
        "upload_root": root / "uploads",
        "max_upload_bytes": 1_000,
        "storage_backend": "memory",
        "sqlite_path": root / "app.sqlite3",
        "document_retention_days": 90,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
