from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.providers.storage import LocalStorageService, StorageError, build_document_storage


class LocalStorageServiceTests(unittest.TestCase):
    def test_build_document_storage_returns_local_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = build_document_storage("local", Path(temp_dir), max_upload_bytes=100)

            stored = storage.save_upload("invoice.pdf", "application/pdf", b"%PDF- demo")

            self.assertTrue(storage.open_for_parser(stored.storage_key).exists())

    def test_s3_storage_backend_is_reserved_until_adapter_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(StorageError):
                build_document_storage("s3", Path(temp_dir), max_upload_bytes=100)

    def test_saves_pdf_with_generated_storage_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir), max_upload_bytes=100)

            stored = storage.save_upload("../../../invoice.pdf", "application/pdf", b"%PDF- demo")

            self.assertTrue(stored.storage_key.endswith(".pdf"))
            self.assertEqual(stored.original_filename, "invoice.pdf")
            self.assertTrue(storage.open_for_parser(stored.storage_key).exists())

    def test_duplicate_original_filenames_get_distinct_storage_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir), max_upload_bytes=100)

            first = storage.save_upload("invoice.pdf", "application/pdf", b"%PDF- one")
            second = storage.save_upload("invoice.pdf", "application/pdf", b"%PDF- two")

            self.assertNotEqual(first.storage_key, second.storage_key)

    def test_rejects_non_pdf_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))

            with self.assertRaises(StorageError):
                storage.save_upload("invoice.txt", "application/pdf", b"%PDF- demo")

    def test_rejects_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))

            with self.assertRaises(StorageError):
                storage.save_upload("invoice.pdf", "application/pdf", b"")

    def test_rejects_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir), max_upload_bytes=5)

            with self.assertRaises(StorageError):
                storage.save_upload("invoice.pdf", "application/pdf", b"%PDF- demo")

    def test_rejects_invalid_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))

            with self.assertRaises(StorageError):
                storage.save_upload("invoice.pdf", "application/pdf", b"not a pdf")

    def test_rejects_invalid_content_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))

            with self.assertRaises(StorageError):
                storage.save_upload("invoice.pdf", "application/octet-stream", b"%PDF- demo")

    def test_streaming_upload_rejects_oversized_before_final_save(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir), max_upload_bytes=5)

            with self.assertRaises(StorageError):
                storage.save_upload_stream(
                    "invoice.pdf",
                    "application/pdf",
                    [b"%PDF-", b" too much"],
                )

            self.assertEqual(list(Path(temp_dir).glob("*.pdf")), [])

    def test_rejects_path_traversal_storage_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))

            with self.assertRaises(StorageError):
                storage.open_for_parser("../secret.pdf")

    def test_delete_removes_stored_pdf_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageService(Path(temp_dir))
            stored = storage.save_upload("invoice.pdf", "application/pdf", b"%PDF- demo")

            storage.delete(stored.storage_key)
            storage.delete(stored.storage_key)

            self.assertFalse((Path(temp_dir) / stored.storage_key).exists())


if __name__ == "__main__":
    unittest.main()
