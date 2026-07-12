from __future__ import annotations

from app.integrations.models import (
    IntegrationDeliveryError,
    IntegrationExportResult,
    IntegrationInvoicePayload,
)


class MockAccountingAdapter:
    name = "mock-accounting"

    def __init__(
        self,
        *,
        fail_invoice_numbers: set[str] | None = None,
        retryable_failures: bool = True,
    ) -> None:
        self.fail_invoice_numbers = fail_invoice_numbers or set()
        self.retryable_failures = retryable_failures
        self.sent_payloads: list[IntegrationInvoicePayload] = []

    def send_invoice(self, payload: IntegrationInvoicePayload) -> IntegrationExportResult:
        invoice_number = payload.invoice_number or ""
        if invoice_number in self.fail_invoice_numbers:
            raise IntegrationDeliveryError(
                "Mock accounting adapter failed to deliver invoice",
                code="mock_delivery_failed",
                retryable=self.retryable_failures,
            )
        self.sent_payloads.append(payload)
        external_suffix = invoice_number or payload.document_id
        return IntegrationExportResult(
            adapter_name=self.name,
            external_id=f"mock-ap-{external_suffix}",
        )
