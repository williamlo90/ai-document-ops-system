from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.review.corrections import CorrectionFeedbackService
from app.review.services import ReviewService


@dataclass(frozen=True)
class ReviewModule:
    service: ReviewService
    correction_feedback: CorrectionFeedbackService


def build_review_module(
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> ReviewModule:
    repositories = persistence.documents
    correction_feedback = CorrectionFeedbackService(repositories.correction_events)
    service = ReviewService(
        repositories.documents,
        repositories.reviews,
        repositories.extractions,
        repositories.audits,
        documents.workflow,
        correction_feedback,
        persistence.transactions,
    )
    return ReviewModule(service=service, correction_feedback=correction_feedback)
