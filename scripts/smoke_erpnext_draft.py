from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import load_settings  # noqa: E402
from app.integrations.erpnext_adapter import ERPNextPurchaseInvoiceAdapter  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.integrations.models import IntegrationInvoicePayload  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402


SMOKE_PREFIX = "PHASE6-SMOKE-"


def main() -> None:
    settings = load_settings()
    _require_local_erpnext(settings.erpnext_base_url)
    if not settings.erpnext_api_key or not settings.erpnext_api_secret:
        raise SystemExit("ERPNext integration credentials are required in the ignored .env file.")
    admin_password = os.getenv("ERPNEXT_ADMIN_PASSWORD") or _read_env_value(
        ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"
    )
    if not admin_password:
        raise SystemExit("ERPNEXT_ADMIN_PASSWORD is required for targeted smoke cleanup.")

    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    invoice_number = f"{SMOKE_PREFIX}{suffix}"
    document_id = str(uuid4())
    delivery_key = f"erpnext:phase6-smoke-{uuid4().hex}"
    payload = IntegrationInvoicePayload(
        document_id=document_id,
        workspace_id="phase6-smoke",
        vendor_name="Acme Logistics",
        invoice_number=invoice_number,
        invoice_date="2026-07-01",
        due_date="2026-07-31",
        subtotal="100.00",
        tax="10.00",
        total="110.00",
        currency="USD",
    )

    runtime_client = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        timeout_seconds=settings.erpnext_timeout_seconds,
        allowed_hosts=settings.erpnext_allowed_hosts,
    )
    adapter = ERPNextPurchaseInvoiceAdapter(runtime_client)
    admin = ERPNextAdminClient(
        settings.erpnext_base_url,
        timeout=max(settings.erpnext_timeout_seconds, 180),
    )
    admin.login(admin_password)
    created_name: str | None = None
    try:
        result = adapter.send_invoice(payload, idempotency_key=delivery_key)
        created_name = result.external_id
        found = adapter.find_invoice(
            payload,
            idempotency_key=delivery_key,
            payload_hash=adapter.payload_hash(payload),
        )
        if found is None or found.external_id != created_name or found.provider_docstatus != 0:
            raise SystemExit("ERPNext draft lookup did not reproduce the verified create receipt.")
        print(f"ERPNext draft create: passed ({created_name}, docstatus=0)")
        print("ERPNext provider reconciliation: passed")
    finally:
        _cleanup_smoke_records(admin, delivery_key, expected_name=created_name)
        admin.logout()
    print("ERPNext smoke cleanup: passed (benchmark invoices untouched)")


def _cleanup_smoke_records(
    admin: ERPNextAdminClient,
    delivery_key: str,
    *,
    expected_name: str | None,
) -> None:
    rows = admin.list_documents(
        "Purchase Invoice",
        filters={"custom_invoice_review_delivery_key": delivery_key},
        fields=("name", "bill_no", "docstatus"),
        limit=2,
    )
    if len(rows) > 1:
        raise SystemExit("Smoke cleanup found duplicate delivery keys; no records were deleted.")
    for row in rows:
        name = str(row.get("name") or "")
        bill_no = str(row.get("bill_no") or "")
        docstatus = int(row.get("docstatus") or 0)
        if not name or not bill_no.startswith(SMOKE_PREFIX) or docstatus != 0:
            raise SystemExit("Smoke cleanup refused to delete a non-smoke or non-draft record.")
        if expected_name is not None and name != expected_name:
            raise SystemExit("Smoke cleanup found an unexpected Purchase Invoice name.")
        admin.delete_document("Purchase Invoice", name)


def _require_local_erpnext(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise SystemExit("ERPNext draft smoke is restricted to the local HTTP sandbox.")


if __name__ == "__main__":
    main()
