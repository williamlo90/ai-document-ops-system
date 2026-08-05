from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.persistence import PersistenceModule
from app.review.services import ReviewService


@dataclass(frozen=True, slots=True)
class ReviewModule:
    service: ReviewService


def build_review_module(persistence: PersistenceModule) -> ReviewModule:
    return ReviewModule(
        ReviewService(
            documents=persistence.documents,
            audits=persistence.audits,
            reviews=persistence.reviews,
            corrections=persistence.corrections,
            transactions=persistence.transactions,
        )
    )
