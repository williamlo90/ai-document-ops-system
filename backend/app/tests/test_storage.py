from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.providers.storage import PrivateDocumentStorage


class StorageTests(unittest.TestCase):
    def test_private_storage_round_trip_and_traversal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = PrivateDocumentStorage(Path(temp_dir) / "private")
            key = storage.write(b"%PDF-private")
            self.assertEqual(storage.read(key), b"%PDF-private")
            with self.assertRaises(ValueError):
                storage.read("../outside.pdf")
            storage.delete(key)
            self.assertFalse((storage.root / key).exists())


if __name__ == "__main__":
    unittest.main()
