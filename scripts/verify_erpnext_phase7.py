from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import Settings, load_settings  # noqa: E402
from app.integrations.erpnext_adapter import ERPNextPurchaseInvoiceAdapter  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.integrations.erpnext_mapping import ERPNextBenchmarkMapping  # noqa: E402
from app.integrations.models import IntegrationInvoicePayload  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from erpnext_setup.dataset import load_benchmark_dataset  # noqa: E402
from erpnext_setup.provisioner import MasterDataProvisioner  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402


MANIFEST = ROOT / "examples/erpnext/benchmark_cases.json"
REVIEW_RECORD = ROOT / "_private_data/erpnext-benchmark-phase7/review-draft.json"
VERIFY_PREFIX = "PHASE7-VERIFY-"


def main() -> None:
    args = _parse_args()
    settings = load_settings()
    _require_local_erpnext(settings.erpnext_base_url)
    if not settings.erpnext_api_key or not settings.erpnext_api_secret:
        raise SystemExit("ERPNext integration credentials are required in the ignored .env file.")
    admin_password = os.getenv("ERPNEXT_ADMIN_PASSWORD") or _read_env_value(
        ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"
    )
    if not admin_password:
        raise SystemExit("ERPNEXT_ADMIN_PASSWORD is required for Phase 7 verification.")

    admin = ERPNextAdminClient(
        settings.erpnext_base_url,
        timeout=max(settings.erpnext_timeout_seconds, 180),
    )
    admin.login(admin_password)
    try:
        if args.cleanup_kept:
            _cleanup_kept_draft(admin)
            return
        _verify_and_create_review_draft(settings, admin, keep=args.keep_for_review)
    finally:
        admin.logout()


def _verify_and_create_review_draft(
    settings: Settings, admin: ERPNextAdminClient, *, keep: bool
) -> None:
    if keep and REVIEW_RECORD.exists():
        raise SystemExit(
            f"A kept Phase 7 draft already exists. Clean it first with: "
            f"{sys.executable} scripts/verify_erpnext_phase7.py --cleanup-kept"
        )

    dataset = load_benchmark_dataset(ROOT, MANIFEST)
    MasterDataProvisioner(admin, dataset).verify()
    runtime_client = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        timeout_seconds=settings.erpnext_timeout_seconds,
        allowed_hosts=settings.erpnext_allowed_hosts,
    )
    adapter = ERPNextPurchaseInvoiceAdapter(runtime_client)
    suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    payload = IntegrationInvoicePayload(
        document_id=str(uuid4()),
        workspace_id="phase7-technical-verification",
        vendor_name="Acme Logistics",
        invoice_number=f"{VERIFY_PREFIX}{suffix}",
        invoice_date="2026-07-01",
        due_date="2026-07-31",
        subtotal="100.00",
        tax="10.00",
        total="110.00",
        currency="USD",
    )
    delivery_key = f"erpnext:phase7-verify-{uuid4().hex}"
    mapped = ERPNextBenchmarkMapping().map_invoice(payload)
    expected = mapped.request(delivery_key=delivery_key, document_id=payload.document_id)
    created_name: str | None = None
    verified = False
    try:
        created = adapter.send_invoice(payload, idempotency_key=delivery_key)
        created_name = created.external_id

        # A fresh client simulates provider reconciliation after an application restart.
        restarted_adapter = ERPNextPurchaseInvoiceAdapter(
            ERPNextClient(
                settings.erpnext_base_url,
                api_key=settings.erpnext_api_key,
                api_secret=settings.erpnext_api_secret,
                timeout_seconds=settings.erpnext_timeout_seconds,
                allowed_hosts=settings.erpnext_allowed_hosts,
            )
        )
        found = restarted_adapter.find_invoice(
            payload,
            idempotency_key=delivery_key,
            payload_hash=mapped.payload_hash,
        )
        if found is None or found.external_id != created_name:
            raise SystemExit("Fresh-client ERPNext reconciliation did not find the created draft.")

        provider_document = admin.get_document("Purchase Invoice", created_name)
        _verify_provider_values(provider_document, expected, mapped.source_total)
        verified = True
        print(f"ERPNext Phase 7 draft: verified ({created_name}, docstatus=0)")
        print("Local-to-ERP field comparison: passed")
        print("Fresh-client reconciliation and duplicate lookup: passed")
        print("Purchase Invoice submit and Payment Entry permissions: absent")

        if keep:
            _write_review_record(
                base_url=settings.erpnext_base_url,
                name=created_name,
                delivery_key=delivery_key,
                payload=payload,
            )
            print(f"Review draft retained: {runtime_client.document_url(created_name)}")
            print(f"Private cleanup record: {REVIEW_RECORD}")
    finally:
        if created_name is not None and (not keep or not verified):
            _cleanup_exact_draft(
                admin,
                delivery_key=delivery_key,
                expected_name=created_name,
            )
            print("ERPNext Phase 7 cleanup: passed")


def _verify_provider_values(
    actual: dict[str, object],
    expected: dict[str, object],
    source_total: Decimal,
) -> None:
    text_fields = (
        "doctype",
        "company",
        "supplier",
        "posting_date",
        "bill_no",
        "bill_date",
        "due_date",
        "currency",
        "credit_to",
        "custom_invoice_review_delivery_key",
        "custom_invoice_review_document_id",
        "custom_invoice_review_payload_hash",
    )
    mismatches = [
        field
        for field in text_fields
        if str(actual.get(field) or "") != str(expected.get(field) or "")
    ]
    if int(str(actual.get("docstatus") or 0)) != 0:
        mismatches.append("docstatus")
    if _money(actual.get("grand_total")) != source_total:
        mismatches.append("grand_total")

    expected_items = expected.get("items")
    actual_items = actual.get("items")
    if not isinstance(expected_items, list) or not isinstance(actual_items, list):
        mismatches.append("items")
    elif len(expected_items) != len(actual_items):
        mismatches.append("items.length")
    else:
        for index, (expected_item, actual_item) in enumerate(
            zip(expected_items, actual_items, strict=True), start=1
        ):
            if not isinstance(expected_item, dict) or not isinstance(actual_item, dict):
                mismatches.append(f"items[{index}]")
                continue
            for field in ("item_code", "expense_account", "uom"):
                if str(actual_item.get(field) or "") != str(expected_item.get(field) or ""):
                    mismatches.append(f"items[{index}].{field}")
            for field in ("qty", "rate"):
                if _decimal(actual_item.get(field)) != _decimal(expected_item.get(field)):
                    mismatches.append(f"items[{index}].{field}")

    if mismatches:
        raise SystemExit(
            "ERPNext draft differs from the approved local payload: " + ", ".join(mismatches)
        )


def _write_review_record(
    *,
    base_url: str,
    name: str,
    delivery_key: str,
    payload: IntegrationInvoicePayload,
) -> None:
    REVIEW_RECORD.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_RECORD.write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "erpnext_name": name,
                "erpnext_url": f"{base_url.rstrip('/')}/app/purchase-invoice/{name}",
                "delivery_key": delivery_key,
                "invoice_number": payload.invoice_number,
                "vendor": payload.vendor_name,
                "total": payload.total,
                "currency": payload.currency,
                "expected_docstatus": 0,
                "cleanup_command": (
                    f"{sys.executable} scripts/verify_erpnext_phase7.py --cleanup-kept"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _cleanup_kept_draft(admin: ERPNextAdminClient) -> None:
    if not REVIEW_RECORD.is_file():
        raise SystemExit("No retained Phase 7 review draft is recorded.")
    record = json.loads(REVIEW_RECORD.read_text(encoding="utf-8"))
    _cleanup_exact_draft(
        admin,
        delivery_key=str(record["delivery_key"]),
        expected_name=str(record["erpnext_name"]),
    )
    REVIEW_RECORD.unlink()
    print("Retained Phase 7 review draft removed.")


def _cleanup_exact_draft(
    admin: ERPNextAdminClient,
    *,
    delivery_key: str,
    expected_name: str,
) -> None:
    rows = admin.list_documents(
        "Purchase Invoice",
        filters={"custom_invoice_review_delivery_key": delivery_key},
        fields=("name", "bill_no", "docstatus"),
        limit=2,
    )
    if len(rows) != 1:
        raise SystemExit("Phase 7 cleanup requires exactly one matching ERPNext draft.")
    row = rows[0]
    name = str(row.get("name") or "")
    bill_no = str(row.get("bill_no") or "")
    docstatus = int(row.get("docstatus") or 0)
    if name != expected_name or not bill_no.startswith(VERIFY_PREFIX) or docstatus != 0:
        raise SystemExit("Phase 7 cleanup refused to delete an unexpected or non-draft record.")
    admin.delete_document("Purchase Invoice", name)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Phase 7 ERPNext safety boundary.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--keep-for-review",
        action="store_true",
        help="Retain one verified non-benchmark draft for manual ERPNext inspection.",
    )
    group.add_argument(
        "--cleanup-kept",
        action="store_true",
        help="Safely remove the draft recorded by --keep-for-review.",
    )
    return parser.parse_args()


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _money(value: object) -> Decimal:
    return _decimal(value).quantize(Decimal("0.01"))


def _require_local_erpnext(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise SystemExit("Phase 7 verification is restricted to the local HTTP sandbox.")


if __name__ == "__main__":
    main()
