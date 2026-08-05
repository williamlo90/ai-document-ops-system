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
        fail_once_invoice_numbers: set[str] | None = None,
        unknown_outcome_invoice_numbers: set[str] | None = None,
        retryable_failures: bool = True,
    ) -> None:
        self.fail_invoice_numbers = fail_invoice_numbers or set()
        self.fail_once_invoice_numbers = fail_once_invoice_numbers or set()
        self.unknown_outcome_invoice_numbers = unknown_outcome_invoice_numbers or set()
        self.retryable_failures = retryable_failures
        self.sent_payloads: list[IntegrationInvoicePayload] = []
        self.attempted_keys: list[str] = []
        self.results_by_key: dict[str, IntegrationExportResult] = {}

    def send_invoice(
        self,
        payload: IntegrationInvoicePayload,
        *,
        idempotency_key: str,
    ) -> IntegrationExportResult:
        self.attempted_keys.append(idempotency_key)
        existing = self.results_by_key.get(idempotency_key)
        if existing is not None:
            return existing
        invoice_number = payload.invoice_number or ""
        if invoice_number in self.fail_once_invoice_numbers:
            self.fail_once_invoice_numbers.remove(invoice_number)
            raise IntegrationDeliveryError(
                "Mock accounting adapter failed before accepting invoice",
                code="mock_delivery_failed_once",
                retryable=True,
            )
        if invoice_number in self.unknown_outcome_invoice_numbers:
            self.unknown_outcome_invoice_numbers.remove(invoice_number)
            self.sent_payloads.append(payload)
            raise IntegrationDeliveryError(
                "Mock accounting adapter timed out after accepting invoice",
                code="mock_delivery_outcome_unknown",
                retryable=False,
                outcome_unknown=True,
            )
        if invoice_number in self.fail_invoice_numbers:
            raise IntegrationDeliveryError(
                "Mock accounting adapter failed to deliver invoice",
                code="mock_delivery_failed",
                retryable=self.retryable_failures,
            )
        self.sent_payloads.append(payload)
        external_suffix = invoice_number or payload.document_id
        result = IntegrationExportResult(
            adapter_name=self.name,
            external_id=f"mock-ap-{external_suffix}",
        )
        self.results_by_key[idempotency_key] = result
        return result
