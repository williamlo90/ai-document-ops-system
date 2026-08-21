from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Protocol

from app.integrations.erpnext_mapping import ERPNextBenchmarkMapping, ERPNextMappedInvoice
from app.integrations.models import (
    IntegrationDeliveryError,
    IntegrationExportResult,
    IntegrationInvoicePayload,
)


class ERPNextPurchaseInvoiceClient(Protocol):
    def create_purchase_invoice(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def find_purchase_invoices_by_delivery_key(self, delivery_key: str) -> list[dict[str, Any]]: ...

    def get_purchase_invoice(self, name: str) -> dict[str, Any]: ...

    def document_url(self, name: str) -> str: ...


class ERPNextPurchaseInvoiceAdapter:
    name = "erpnext-purchase-invoice-draft"
    event_prefix = "erp_draft"

    def __init__(
        self,
        client: ERPNextPurchaseInvoiceClient,
        mapping: ERPNextBenchmarkMapping | None = None,
    ) -> None:
        self.client = client
        self.mapping = mapping or ERPNextBenchmarkMapping()

    def payload_hash(self, payload: IntegrationInvoicePayload) -> str:
        return self.mapping.map_invoice(payload).payload_hash

    def send_invoice(
        self,
        payload: IntegrationInvoicePayload,
        *,
        idempotency_key: str,
    ) -> IntegrationExportResult:
        mapped = self.mapping.map_invoice(payload)
        response = self.client.create_purchase_invoice(
            mapped.request(
                delivery_key=idempotency_key,
                document_id=payload.document_id,
            )
        )
        return self._verified_result(
            response,
            mapped=mapped,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def find_invoice(
        self,
        payload: IntegrationInvoicePayload,
        *,
        idempotency_key: str,
        payload_hash: str,
    ) -> IntegrationExportResult | None:
        mapped = self.mapping.map_invoice(payload)
        if mapped.payload_hash != payload_hash:
            raise IntegrationDeliveryError(
                "Approved invoice data changed after delivery was reserved",
                code="erpnext_payload_changed",
                retryable=False,
            )
        matches = self.client.find_purchase_invoices_by_delivery_key(idempotency_key)
        if not matches:
            return None
        if len(matches) != 1:
            raise IntegrationDeliveryError(
                "ERPNext contains multiple records for one delivery key",
                code="erpnext_duplicate_delivery_key",
                retryable=False,
            )
        name = _required_response_text(matches[0], "name")
        response = self.client.get_purchase_invoice(name)
        return self._verified_result(
            response,
            mapped=mapped,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def _verified_result(
        self,
        response: dict[str, Any],
        *,
        mapped: ERPNextMappedInvoice,
        payload: IntegrationInvoicePayload,
        idempotency_key: str,
    ) -> IntegrationExportResult:
        name = _required_response_text(response, "name")
        raw_docstatus = response.get("docstatus")
        if raw_docstatus is None:
            raise _unsafe("ERPNext response is missing Draft status")
        try:
            docstatus = int(raw_docstatus)
        except (TypeError, ValueError) as exc:
            raise _unsafe("ERPNext response is missing Draft status") from exc
        if docstatus != 0:
            raise _unsafe("ERPNext returned a Purchase Invoice that is not Draft")

        expected = {
            "doctype": "Purchase Invoice",
            "company": mapped.request_core["company"],
            "supplier": mapped.request_core["supplier"],
            "posting_date": mapped.request_core["posting_date"],
            "bill_no": mapped.request_core["bill_no"],
            "bill_date": mapped.request_core["bill_date"],
            "due_date": mapped.request_core["due_date"],
            "currency": mapped.request_core["currency"],
            "credit_to": mapped.request_core["credit_to"],
            "custom_invoice_review_delivery_key": idempotency_key,
            "custom_invoice_review_document_id": payload.document_id,
            "custom_invoice_review_payload_hash": mapped.payload_hash,
        }
        mismatches = [
            field
            for field, value in expected.items()
            if str(response.get(field) or "") != str(value)
        ]
        if mismatches:
            raise _unsafe(
                "ERPNext draft does not match the approved invoice: " + ", ".join(mismatches)
            )
        try:
            provider_total = Decimal(str(response.get("grand_total"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError) as exc:
            raise _unsafe("ERPNext draft is missing its calculated total") from exc
        if provider_total != mapped.source_total:
            raise _unsafe("ERPNext calculated total does not match the approved invoice")

        return IntegrationExportResult(
            adapter_name=self.name,
            external_id=name,
            external_url=self.client.document_url(name),
            provider_docstatus=docstatus,
            provider_updated_at=(str(response["modified"]) if response.get("modified") else None),
            status="draft_created",
        )


def _required_response_text(response: dict[str, Any], field: str) -> str:
    value = str(response.get(field) or "").strip()
    if not value:
        raise IntegrationDeliveryError(
            "ERPNext returned an incomplete draft receipt",
            code="erpnext_invalid_receipt",
            retryable=False,
            outcome_unknown=True,
        )
    return value


def _unsafe(message: str) -> IntegrationDeliveryError:
    return IntegrationDeliveryError(
        message,
        code="erpnext_unsafe_state",
        retryable=False,
    )
