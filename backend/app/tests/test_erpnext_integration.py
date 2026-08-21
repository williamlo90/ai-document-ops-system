from __future__ import annotations

from copy import deepcopy
from datetime import date
from io import BytesIO
from typing import Any
import unittest
from urllib.error import HTTPError, URLError

from app.integrations.erpnext_adapter import ERPNextPurchaseInvoiceAdapter
from app.integrations.erpnext_client import ERPNextClient, validate_erpnext_base_url
from app.integrations.erpnext_mapping import ERPNextBenchmarkMapping
from app.integrations.models import (
    IntegrationDeliveryError,
    IntegrationInvoicePayload,
    IntegrationLineItem,
    IntegrationMappingError,
)


class FakeERPNextClient:
    def __init__(self, *, grand_total: str = "110.00", docstatus: int = 0) -> None:
        self.grand_total = grand_total
        self.docstatus = docstatus
        self.created: list[dict[str, Any]] = []
        self.documents: dict[str, dict[str, Any]] = {}

    def create_purchase_invoice(self, values: dict[str, Any]) -> dict[str, Any]:
        self.created.append(deepcopy(values))
        name = "ACC-PINV-2026-00001"
        document = {
            **deepcopy(values),
            "name": name,
            "grand_total": self.grand_total,
            "docstatus": self.docstatus,
            "modified": "2026-08-14 08:00:00.000000",
        }
        self.documents[name] = document
        return deepcopy(document)

    def find_purchase_invoices_by_delivery_key(self, delivery_key: str) -> list[dict[str, Any]]:
        return [
            {"name": name, "docstatus": document["docstatus"]}
            for name, document in self.documents.items()
            if document.get("custom_invoice_review_delivery_key") == delivery_key
        ]

    def get_purchase_invoice(self, name: str) -> dict[str, Any]:
        return deepcopy(self.documents[name])

    def document_url(self, name: str) -> str:
        return f"http://127.0.0.1:8080/app/purchase-invoice/{name}"


class StubResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> StubResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class StubOpener:
    def __init__(self, result: StubResponse | Exception) -> None:
        self.result = result
        self.requests: list[Any] = []

    def open(self, request: Any, *, timeout: int) -> StubResponse:
        self.requests.append((request, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class ERPNextMappingTests(unittest.TestCase):
    def test_maps_approved_header_values_to_configured_summary_line(self) -> None:
        mapped = ERPNextBenchmarkMapping(today=lambda: date(2026, 8, 21)).map_invoice(_payload())
        request = mapped.request(delivery_key="erpnext:key", document_id="document-1")

        self.assertEqual(request["company"], "Invoice Review Assisted Benchmark")
        self.assertEqual(request["supplier"], "Acme Logistics - Assisted Benchmark")
        self.assertEqual(request["credit_to"], "Creditors - IRA")
        self.assertEqual(request["docstatus"], 0)
        self.assertEqual(request["set_posting_time"], 1)
        self.assertEqual(request["posting_date"], "2026-08-21")
        self.assertEqual(request["bill_date"], "2026-07-01")
        self.assertEqual(request["due_date"], "2026-07-31")
        self.assertEqual(request["items"][0]["rate"], 100.0)
        self.assertEqual(request["taxes_and_charges"], "Benchmark Input Tax 10% - IRA")
        self.assertEqual(request["taxes"][0]["rate"], 10.0)
        self.assertEqual(request["custom_invoice_review_payload_hash"], mapped.payload_hash)

    def test_maps_complete_source_lines_without_changing_their_amounts(self) -> None:
        payload = _payload(
            line_items=(
                IntegrationLineItem(
                    description="Freight",
                    quantity="2",
                    unit_price="40.00",
                    amount="80.00",
                ),
                IntegrationLineItem(
                    description="Fuel surcharge",
                    quantity="1",
                    unit_price="20.00",
                    amount="20.00",
                ),
            )
        )

        mapped = ERPNextBenchmarkMapping().map_invoice(payload)

        self.assertEqual(len(mapped.request_core["items"]), 2)
        self.assertEqual(mapped.request_core["items"][0]["qty"], 2.0)
        self.assertEqual(mapped.request_core["items"][1]["rate"], 20.0)

    def test_maps_supplier_name_without_case_sensitivity(self) -> None:
        mapped = ERPNextBenchmarkMapping().map_invoice(_payload(vendor_name="  ACME   LOGISTICS  "))

        self.assertEqual(
            mapped.request_core["supplier"],
            "Acme Logistics - Assisted Benchmark",
        )

    def test_maps_fixed_eur_benchmark_rate(self) -> None:
        payload = _payload(
            vendor_name="Rhein Handel GmbH",
            invoice_date="2026-07-03",
            due_date="2026-08-02",
            subtotal="1250.00",
            tax="250.00",
            total="1500.00",
            currency="EUR",
        )

        mapped = ERPNextBenchmarkMapping().map_invoice(payload)

        self.assertEqual(mapped.request_core["conversion_rate"], 1.1)
        self.assertEqual(mapped.request_core["credit_to"], "Creditors EUR - IRA")
        self.assertEqual(
            mapped.request_core["taxes_and_charges"],
            "Benchmark Input Tax 20% - IRA",
        )

    def test_blocks_unknown_supplier_total_mismatch_and_partial_lines(self) -> None:
        cases = (
            _payload(vendor_name="Invented Vendor"),
            _payload(total="125.00"),
            _payload(
                line_items=(
                    IntegrationLineItem(
                        description="Incomplete",
                        quantity="1",
                        unit_price=None,
                        amount="100.00",
                    ),
                )
            ),
        )

        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(IntegrationMappingError):
                ERPNextBenchmarkMapping().map_invoice(payload)


class ERPNextAdapterTests(unittest.TestCase):
    def test_creates_and_verifies_draft_receipt(self) -> None:
        client = FakeERPNextClient()
        adapter = ERPNextPurchaseInvoiceAdapter(client)
        payload = _payload()

        result = adapter.send_invoice(payload, idempotency_key="erpnext:stable-key")

        self.assertEqual(result.status, "draft_created")
        self.assertEqual(result.provider_docstatus, 0)
        self.assertEqual(result.external_id, "ACC-PINV-2026-00001")
        self.assertEqual(len(client.created), 1)
        self.assertEqual(client.created[0]["docstatus"], 0)

    def test_provider_lookup_reconciles_exact_existing_draft(self) -> None:
        client = FakeERPNextClient()
        adapter = ERPNextPurchaseInvoiceAdapter(client)
        payload = _payload()
        payload_hash = adapter.payload_hash(payload)
        adapter.send_invoice(payload, idempotency_key="erpnext:lookup-key")

        result = adapter.find_invoice(
            payload,
            idempotency_key="erpnext:lookup-key",
            payload_hash=payload_hash,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.external_id, "ACC-PINV-2026-00001")

    def test_rejects_provider_document_that_is_not_draft(self) -> None:
        adapter = ERPNextPurchaseInvoiceAdapter(FakeERPNextClient(docstatus=1))

        with self.assertRaises(IntegrationDeliveryError) as caught:
            adapter.send_invoice(_payload(), idempotency_key="erpnext:unsafe-key")

        self.assertEqual(caught.exception.code, "erpnext_unsafe_state")
        self.assertFalse(caught.exception.retryable)

    def test_base_url_policy_allows_local_http_and_rejects_unlisted_host(self) -> None:
        self.assertEqual(
            validate_erpnext_base_url(
                "http://127.0.0.1:8080",
                ("127.0.0.1", "localhost"),
            ),
            "http://127.0.0.1:8080",
        )
        with self.assertRaises(ValueError):
            validate_erpnext_base_url(
                "https://erp.attacker.test",
                ("erp.example.test",),
            )


class ERPNextClientTests(unittest.TestCase):
    def test_client_serializes_purchase_invoice_and_builds_document_url(self) -> None:
        opener = StubOpener(StubResponse(b'{"data":{"name":"ACC-PINV-0001"}}'))
        client = _client(opener)

        result = client.create_purchase_invoice({"supplier": "Acme Logistics"})

        request, timeout = opener.requests[0]
        self.assertEqual(result["name"], "ACC-PINV-0001")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "token key:secret")
        self.assertEqual(request.data, b'{"supplier":"Acme Logistics"}')
        self.assertEqual(timeout, 5)
        self.assertEqual(
            client.document_url("ACC/PINV 0001"),
            "http://127.0.0.1:8080/app/purchase-invoice/ACC%2FPINV%200001",
        )

    def test_client_rejects_invalid_provider_response_shapes(self) -> None:
        cases = (
            ("create", b'{"data":[]} ', "erpnext_invalid_receipt"),
            ("find", b'{"data":[1]}', "erpnext_invalid_lookup"),
            ("get", b'{"data":[]}', "erpnext_invalid_document"),
            ("create", b"[]", "erpnext_invalid_response"),
            ("create", b"not-json", "erpnext_invalid_json"),
        )

        for operation, response, expected_code in cases:
            with self.subTest(operation=operation, expected_code=expected_code):
                client = _client(StubOpener(StubResponse(response)))
                with self.assertRaises(IntegrationDeliveryError) as caught:
                    if operation == "find":
                        client.find_purchase_invoices_by_delivery_key("delivery-key")
                    elif operation == "get":
                        client.get_purchase_invoice("ACC-PINV-0001")
                    else:
                        client.create_purchase_invoice({"supplier": "Acme"})
                self.assertEqual(caught.exception.code, expected_code)

    def test_client_classifies_transport_and_http_failures(self) -> None:
        cases = (
            (URLError("offline"), "erpnext_transport_error", True),
            (_http_error(401, b"{}"), "erpnext_access_denied", False),
            (_http_error(429, b"{}"), "erpnext_rate_limited", False),
            (_http_error(503, b"{}"), "erpnext_server_error", True),
            (
                _http_error(422, b'{"message":"Duplicate supplier invoice"}'),
                "erpnext_duplicate_invoice",
                False,
            ),
            (
                _http_error(422, b'{"message":"Invalid supplier"}'),
                "erpnext_validation_rejected",
                False,
            ),
            (_http_error(422, b"not-json"), "erpnext_validation_rejected", False),
        )

        for failure, expected_code, outcome_unknown in cases:
            with self.subTest(expected_code=expected_code):
                client = _client(StubOpener(failure))
                with self.assertRaises(IntegrationDeliveryError) as caught:
                    client.create_purchase_invoice({"supplier": "Acme"})
                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(caught.exception.outcome_unknown, outcome_unknown)

    def test_base_url_policy_rejects_unsafe_url_components(self) -> None:
        invalid_urls = (
            "ftp://erp.example.test",
            "http://erp.example.test",
            "https://erp.example.test:8443",
            "https://user:password@erp.example.test",
            "https://erp.example.test/api",
            "https://erp.example.test?debug=true",
            "https://erp.example.test#fragment",
            "https://erp.example.test:invalid",
        )

        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_erpnext_base_url(url, ("erp.example.test",))


def _payload(
    *,
    vendor_name: str = "Acme Logistics",
    invoice_date: str = "2026-07-01",
    due_date: str = "2026-07-31",
    subtotal: str = "100.00",
    tax: str = "10.00",
    total: str = "110.00",
    currency: str = "USD",
    line_items: tuple[IntegrationLineItem, ...] = (),
) -> IntegrationInvoicePayload:
    return IntegrationInvoicePayload(
        document_id="11111111-1111-4111-8111-111111111111",
        workspace_id="default",
        vendor_name=vendor_name,
        invoice_number="AC-1001",
        invoice_date=invoice_date,
        due_date=due_date,
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency=currency,
        line_items=line_items,
    )


def _client(opener: StubOpener) -> ERPNextClient:
    client = ERPNextClient(
        "http://127.0.0.1:8080",
        api_key="key",
        api_secret="secret",
        timeout_seconds=5,
        allowed_hosts=("127.0.0.1",),
    )
    client._opener = opener
    return client


def _http_error(status: int, body: bytes) -> HTTPError:
    return HTTPError(
        "http://127.0.0.1:8080/api/resource/Purchase%20Invoice",
        status,
        "ERPNext error",
        None,
        BytesIO(body),
    )


if __name__ == "__main__":
    unittest.main()
