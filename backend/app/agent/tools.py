from __future__ import annotations

from uuid import UUID

from app.agent.models import Citation
from app.review.services import ReviewRepository


class ReadOnlyInvoiceTools:
    def __init__(self, reviews: ReviewRepository) -> None:
        self.reviews = reviews

    def field(self, document_id: UUID, name: str) -> Citation | None:
        record = self.reviews.get(document_id)
        if record is None or not hasattr(record.current, name):
            return None
        value = getattr(record.current, name)
        if value is None:
            return None
        return Citation(document_id, name, str(value))
