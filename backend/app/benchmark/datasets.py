from __future__ import annotations

from dataclasses import dataclass

from app.extraction.schemas import InvoiceData
from app.review.datasets import sample_invoice


DATASET_VERSION = "invoice-scenarios-v1"


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    pdf: bytes
    expected: InvoiceData


def scenarios() -> tuple[Scenario, ...]:
    return (
        Scenario("clean", b"%PDF-clean", sample_invoice()),
        Scenario("total-mismatch", b"%PDF-total-mismatch", sample_invoice(total="111.00")),
        Scenario("repeat-clean", b"%PDF-repeat", sample_invoice()),
    )
