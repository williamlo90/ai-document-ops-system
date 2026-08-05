from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.bootstrap.container import build_container
from app.core.settings import Settings
from app.documents.models import DocumentRecord
from app.documents.status import DocumentStatus
from app.review.datasets import sample_invoice


class CorrectionFeedbackTests(unittest.TestCase):
    def test_field_level_before_after_actor_reason_persists_in_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(persistence_backend="sqlite", sqlite_path=Path(temp_dir) / "app.sqlite3")
            first = build_container(settings)
            document = DocumentRecord("invoice.pdf", "key", "application/pdf", status=DocumentStatus.NEEDS_REVIEW)
            with first.persistence.transactions.transaction():
                first.persistence.documents.add(document)
            first.review_module.service.seed(document.id, sample_invoice(total="111.00"))
            first.review_module.service.correct(document.id, field_name="total", value="110.00", actor="Maya Chen", reason="Matched PDF total")
            first.close()

            second = build_container(settings)
            try:
                record = second.persistence.reviews.get(document.id)
                event = second.persistence.corrections.list_for_document(document.id)[0]
                self.assertEqual(str(record.original.total), "111.00")  # type: ignore[union-attr]
                self.assertEqual(str(record.current.total), "110.00")  # type: ignore[union-attr]
                self.assertEqual((event.before, event.after, event.actor, event.reason), ("111.00", "110.00", "Maya Chen", "Matched PDF total"))
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
