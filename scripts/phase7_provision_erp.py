"""Author one synthetic release invoice and provision its isolated sandbox PO/receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from app.core.settings import load_settings
from app.integrations.erpnext_client import ERPNextClient
from app.procurement.erpnext import read_procurement
from erpnext_setup.api import ERPNextAdminClient
from phase7_demo import author
from provision_erpnext_master_data import _read_env_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if ROOT / "_local_docs" not in directory.parents:
        raise SystemExit("Provisioning records must stay under ignored _local_docs")
    settings = load_settings()
    if settings.erpnext_base_url != "http://127.0.0.1:8080" or not settings.accounting_sandbox_mode:
        raise SystemExit("The existing explicitly configured local sandbox is required")
    fixture = author(directory, uuid4().hex[:10].upper())
    supplier, item, company = "Acme Logistics", "Release Kit", fixture["company"]
    admin = ERPNextAdminClient(settings.erpnext_base_url, timeout=60)
    admin.login(_read_env_value(ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"))
    try:
        if not admin.find_one("Supplier", {"supplier_name": supplier}):
            admin.create_document(
                "Supplier",
                {
                    "supplier_name": supplier,
                    "supplier_group": "All Supplier Groups",
                    "supplier_type": "Company",
                    "default_currency": "USD",
                },
            )
        if not admin.find_one("Item", {"item_code": item}):
            admin.create_document(
                "Item",
                {
                    "item_code": item,
                    "item_name": item,
                    "item_group": "All Item Groups",
                    "stock_uom": "EA",
                    "is_stock_item": 0,
                    "is_purchase_item": 1,
                },
            )
        line = {
            "item_code": item,
            "qty": 2,
            "rate": 50,
            "uom": "EA",
            "expense_account": "Professional Services - IRA",
            "cost_center": "Main - IRA",
        }
        tag = "Phase7:" + fixture["invoice"]["invoice_number"]
        po = admin.create_document(
            "Purchase Order",
            {
                "company": company,
                "supplier": supplier,
                "transaction_date": "2026-06-18",
                "schedule_date": "2026-06-19",
                "currency": "USD",
                "terms": tag,
                "items": [{**line, "schedule_date": "2026-06-19"}],
            },
        )
        admin.call_method("frappe.client.submit", values={"doc": json.dumps(po)})
        po = admin.get_document("Purchase Order", po["name"])
        receipt = admin.create_document(
            "Purchase Receipt",
            {
                "company": company,
                "supplier": supplier,
                "posting_date": "2026-06-19",
                "set_posting_time": 1,
                "currency": "USD",
                "remarks": tag,
                "items": [
                    {
                        **line,
                        "purchase_order": po["name"],
                        "purchase_order_item": po["items"][0]["name"],
                    }
                ],
            },
        )
        admin.call_method("frappe.client.submit", values={"doc": json.dumps(receipt)})
        erp = ERPNextClient(
            settings.erpnext_base_url,
            api_key=settings.erpnext_api_key,
            api_secret=settings.erpnext_api_secret,
            allowed_hosts=settings.erpnext_allowed_hosts,
            timeout_seconds=60,
        )
        fixture["sources"] = [
            read_procurement(erp, "po", po["name"], "Asia/Jakarta").model_dump(mode="json"),
            read_procurement(erp, "receipt", receipt["name"], "Asia/Jakarta").model_dump(
                mode="json"
            ),
        ]
        fixture["profile"] = {
            "company": company,
            "erp_company": company,
            "supplier_ids": {supplier: supplier},
            "item_codes": {item: item},
            "expense_accounts": {item: "Professional Services - IRA"},
            "payable_accounts": {"USD": "Creditors - IRA"},
            "exchange_rates": {"USD": "1"},
            "reason": "Verified local release sandbox mappings",
        }
        (directory / "fixture.json").write_text(
            json.dumps(fixture, indent=2) + "\n", encoding="utf-8"
        )
        print("Release fixture provisioned; no Purchase Invoice or payment was created.")
    finally:
        admin.logout()


if __name__ == "__main__":
    main()
