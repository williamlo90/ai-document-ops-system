from __future__ import annotations

from dataclasses import dataclass

from app.bootstrap.documents import DocumentModule
from app.bootstrap.persistence import PersistenceModule
from app.core.settings import Settings
from app.integrations.adapters import MockAccountingAdapter
from app.integrations.erpnext_adapter import ERPNextPurchaseInvoiceAdapter
from app.integrations.erpnext_client import ERPNextClient
from app.integrations.models import AccountingIntegrationAdapter
from app.integrations.services import InvoiceIntegrationService


@dataclass(frozen=True)
class IntegrationModule:
    service: InvoiceIntegrationService


def build_integration_module(
    settings: Settings,
    documents: DocumentModule,
    persistence: PersistenceModule,
) -> IntegrationModule:
    repositories = persistence.documents
    adapter = _accounting_adapter(settings)
    return IntegrationModule(
        service=InvoiceIntegrationService(
            repositories.documents,
            repositories.extractions,
            repositories.reviews,
            repositories.audits,
            documents.workflow,
            adapter,
            persistence.integration_deliveries,
            persistence.transactions,
            documents.state_writer,
        )
    )


def _accounting_adapter(settings: Settings) -> AccountingIntegrationAdapter:
    provider = settings.accounting_provider.strip().casefold()
    if provider != "erpnext":
        return MockAccountingAdapter()
    if not settings.erpnext_api_key or not settings.erpnext_api_secret:
        raise ValueError("ERPNext API credentials are required when ACCOUNTING_PROVIDER=erpnext")
    client = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        timeout_seconds=settings.erpnext_timeout_seconds,
        allowed_hosts=settings.erpnext_allowed_hosts,
    )
    return ERPNextPurchaseInvoiceAdapter(client)
