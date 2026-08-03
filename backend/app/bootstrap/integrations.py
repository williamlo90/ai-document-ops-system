from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.integrations.adapters import MockAccountingAdapter
from app.integrations.services import InvoiceIntegrationService


@dataclass(frozen=True)
class IntegrationModule:
    service: InvoiceIntegrationService


def build_integration_module(
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> IntegrationModule:
    repositories = persistence.documents
    return IntegrationModule(
        service=InvoiceIntegrationService(
            repositories.documents,
            repositories.extractions,
            repositories.audits,
            documents.workflow,
            MockAccountingAdapter(),
            persistence.integration_deliveries,
            persistence.transactions,
        )
    )
