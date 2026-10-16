"""Provision and bind synthetic Phase 6 sources in the explicitly enabled local ERP sandbox."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.core.settings import load_settings  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.procurement.erpnext import read_procurement  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402

COMPANY = "Invoice Review Assisted Benchmark"
EXPENSE = "Professional Services - IRA"
PAYABLE = "Creditors - IRA"


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def configure_price_policy(pack: Path):
    """The AP policy enforces tolerance; ERP retains its rate-variance warning."""
    pack = pack.resolve()
    if (
        ROOT not in pack.parents
        or "_local_docs" not in pack.parts
        or load_json(pack / "manifest.json")["status"] != "planned"
    ):
        raise ValueError("Price policy setup requires an unsealed local pack")
    settings = load_settings()
    if (
        urlparse(settings.erpnext_base_url).hostname not in {"localhost", "127.0.0.1"}
        or not settings.accounting_sandbox_mode
        or not settings.erpnext_sandbox_posting_enabled
    ):
        raise ValueError("Explicit local ERP sandbox required")
    admin = ERPNextAdminClient(settings.erpnext_base_url, timeout=60)
    admin.login(_read_env_value(ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"))
    try:
        before = admin.get_document("Buying Settings", "Buying Settings")
        fields = {"maintain_same_rate": 1, "maintain_same_rate_action": "Warn"}
        admin.update_document("Buying Settings", "Buying Settings", fields)
        after = admin.get_document("Buying Settings", "Buying Settings")
        if any(after.get(key) != value for key, value in fields.items()):
            raise ValueError("ERP did not apply the synthetic purchasing policy")
        allowances = {}
        for cohort in load_json(pack / "manifest.json")["cohorts"]:
            if cohort["split"] != "development":
                continue
            for family in cohort["families"]:
                directory = pack / "development" / family["family_id"]
                for revision in load_json(directory / "corrections.json")["events"]:
                    if revision["kind"] == "price_tolerance_change":
                        line = load_json(directory / "procurement.json")["purchase_order"]["lines"][
                            0
                        ]
                        allowance = (
                            Decimal(revision["absolute_tolerance"])
                            / Decimal(line["unit_price"])
                            * 100
                        ).quantize(Decimal("1"), rounding=ROUND_CEILING)
                        admin.update_document(
                            "Item", line["item_id"], {"over_billing_allowance": str(allowance)}
                        )
                        allowances[line["item_id"]] = str(allowance)
        account_settings = {
            "over_billing_allowance": max(
                (Decimal(value) for value in allowances.values()), default=Decimal(0)
            )
        }
        admin.update_document(
            "Accounts Settings",
            "Accounts Settings",
            {key: str(value) for key, value in account_settings.items()},
        )
        write(
            pack / "erp-environment.json",
            {
                "site_timezone": "Asia/Jakarta",
                "buying_settings": fields,
                "accounts_settings": {key: str(value) for key, value in account_settings.items()},
                "item_billing_allowances_percent": allowances,
                "previous_buying_settings": {key: before.get(key) for key in fields},
                "scope": "local synthetic sandbox; AP approval policy enforces exact or explicitly versioned tolerance",
            },
        )
        return {"status": "configured", "buying_settings": fields}
    finally:
        admin.logout()


def prepare(
    pack: Path,
    *,
    splits=("quality_holdout", "time_study"),
    max_families=None,
    development_probes=False,
    development_revisions=False,
) -> dict:
    pack = pack.resolve()
    if ROOT not in pack.parents or "_local_docs" not in pack.parts:
        raise ValueError("ERP fixtures must remain inside ignored local evidence")
    manifest = load_json(pack / "manifest.json")
    if manifest["status"] != "planned":
        raise ValueError("Cannot change ERP bindings after seal")
    audit(pack, inspect_pdf_text=False)
    settings = load_settings()
    if (
        urlparse(settings.erpnext_base_url).hostname not in {"localhost", "127.0.0.1"}
        or not settings.accounting_sandbox_mode
        or not settings.erpnext_sandbox_posting_enabled
    ):
        raise ValueError("Explicit local ERP sandbox flags are required")
    admin = ERPNextAdminClient(settings.erpnext_base_url, timeout=60)
    admin.login(_read_env_value(ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"))
    runtime = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        allowed_hosts=settings.erpnext_allowed_hosts,
        timeout_seconds=60,
    )
    profile = {
        "company": COMPANY,
        "erp_company": COMPANY,
        "supplier_ids": {},
        "item_codes": {},
        "expense_accounts": {},
        "payable_accounts": {"USD": PAYABLE},
        "exchange_rates": {"USD": "1"},
        "reason": "Verified Phase 6 local synthetic sandbox master data",
    }
    if (pack / "erp-profile.json").exists():
        profile = load_json(pack / "erp-profile.json")
    journal_path = pack / "erp-provision-journal.json"
    journal = load_json(journal_path) if journal_path.exists() else {"families": {}}
    try:
        for account in (EXPENSE, PAYABLE):
            if admin.get_document("Account", account)["company"] != COMPANY:
                raise ValueError("Sandbox account company differs")
        if not admin.find_one("UOM", {"name": "EA"}):
            admin.create_document("UOM", {"uom_name": "EA", "must_be_whole_number": 1})
        for cohort in manifest["cohorts"]:
            if cohort["split"] not in splits:
                continue
            split = cohort["split"]
            families = cohort["families"][:max_families]
            if development_probes:
                families = [family for index, family in enumerate(families) if index % 10 == 1]
            if development_revisions:
                families = [family for family in families if family["counts"]["rule_revisions"]]
            for family in families:
                family_id = family["family_id"]
                directory = pack / split / family_id
                sources = load_json(directory / "procurement.json")
                original = sources["purchase_order"]
                supplier = original["supplier_id"]
                item = original["lines"][0]["item_id"]
                if not admin.find_one("Supplier", {"name": supplier}):
                    created = admin.create_document(
                        "Supplier",
                        {
                            "supplier_name": supplier,
                            "supplier_group": "All Supplier Groups",
                            "supplier_type": "Company",
                        },
                    )
                    if created["name"] != supplier:
                        raise ValueError("Supplier naming differs from fixture identity")
                if not admin.find_one("Item", {"name": item}):
                    admin.create_document(
                        "Item",
                        {
                            "item_code": item,
                            "item_name": item,
                            "item_group": "Services",
                            "stock_uom": "EA",
                            "is_stock_item": 0,
                            "is_purchase_item": 1,
                            "is_sales_item": 0,
                        },
                    )
                profile["supplier_ids"][supplier] = supplier
                profile["item_codes"][item] = item
                profile["expense_accounts"][item] = EXPENSE
                journal["families"].setdefault(family_id, {})
                matches = load_json(directory / "expected-match.json")
                # Separate manual and assisted source instances prevent the second
                # condition from consuming the first condition's quantity capacity.
                conditions = ("assisted", "manual") if split == "time_study" else ("quality",)
                for condition in conditions:
                    tag = f"Phase6:{family_id}:{condition}"
                    saved = journal["families"][family_id].setdefault(condition, {})
                    po = admin.find_one("Purchase Order", {"terms": tag})
                    date = load_json(directory / "invoice-labels.json")[0]["invoice_date"]
                    line = original["lines"][0]
                    if po is None:
                        po = admin.create_document(
                            "Purchase Order",
                            {
                                "company": COMPANY,
                                "supplier": supplier,
                                "transaction_date": date,
                                "schedule_date": date,
                                "currency": "USD",
                                "terms": tag,
                                "items": [
                                    {
                                        "item_code": item,
                                        "qty": line["quantity"],
                                        "rate": line["unit_price"],
                                        "uom": "EA",
                                        "schedule_date": date,
                                        "expense_account": EXPENSE,
                                        "cost_center": "Main - IRA",
                                    }
                                ],
                            },
                        )
                    po = admin.get_document("Purchase Order", po["name"])
                    saved["po"] = po["name"]
                    write(journal_path, journal)
                    if po["docstatus"] == 0:
                        admin.call_method("frappe.client.submit", values={"doc": json.dumps(po)})
                    po = admin.get_document("Purchase Order", po["name"])
                    receipt = admin.find_one("Purchase Receipt", {"remarks": tag})
                    receipt_line = sources["purchase_receipt"]["lines"][0]
                    if receipt is None:
                        receipt = admin.create_document(
                            "Purchase Receipt",
                            {
                                "company": COMPANY,
                                "supplier": supplier,
                                "posting_date": date,
                                "set_posting_time": 1,
                                "currency": "USD",
                                "remarks": tag,
                                "items": [
                                    {
                                        "item_code": item,
                                        "qty": receipt_line["quantity"],
                                        "rate": line["unit_price"],
                                        "uom": "EA",
                                        "purchase_order": po["name"],
                                        "purchase_order_item": po["items"][0]["name"],
                                        "expense_account": EXPENSE,
                                        "cost_center": "Main - IRA",
                                    }
                                ],
                            },
                        )
                    receipt = admin.get_document("Purchase Receipt", receipt["name"])
                    saved["receipt"] = receipt["name"]
                    write(journal_path, journal)
                    if receipt["docstatus"] == 0:
                        admin.call_method(
                            "frappe.client.submit", values={"doc": json.dumps(receipt)}
                        )
                    live_po = read_procurement(
                        runtime, "po", po["name"], "Asia/Jakarta"
                    ).model_dump(mode="json")
                    live_pr = read_procurement(
                        runtime, "receipt", receipt["name"], "Asia/Jakarta"
                    ).model_dump(mode="json")
                    # Verify business semantics against the authored specification,
                    # before replacing only ERP identity/version fields in the pack.
                    for live, authored in (
                        (live_po, original),
                        (live_pr, sources["purchase_receipt"]),
                    ):
                        if (
                            live["status"] != "submitted"
                            or live["supplier_id"] != supplier
                            or live["company"] != COMPANY
                        ):
                            raise ValueError(
                                "ERP source identity/status differs from authored fixture"
                            )
                        for field in ("quantity", "unit_price", "amount"):
                            if Decimal(live["lines"][0][field]) != Decimal(
                                authored["lines"][0][field]
                            ):
                                raise ValueError(
                                    "ERP source arithmetic differs from authored fixture"
                                )
                    key_prefix = "manual_" if condition == "manual" else ""
                    sources[key_prefix + "purchase_order"] = live_po
                    sources[key_prefix + "purchase_receipt"] = live_pr
                    if condition != "manual":
                        for match in matches:
                            match["po_allocation"] = (
                                f"{live_po['source_id']}:{live_po['lines'][0]['source_line_id']}"
                            )
                            match["receipt_allocation"] = (
                                f"{live_pr['source_id']}:{live_pr['lines'][0]['source_line_id']}"
                            )
                revisions = load_json(directory / "corrections.json")["events"]
                for revision in revisions:
                    if revision["kind"] != "receipt_quantity_correction":
                        continue
                    old_receipt = admin.get_document(
                        "Purchase Receipt", sources["purchase_receipt"]["source_id"]
                    )
                    tag = f"Phase6:{family_id}:corrected"
                    corrected = admin.find_one("Purchase Receipt", {"remarks": tag})
                    if old_receipt["docstatus"] == 1:
                        admin.call_method(
                            "frappe.client.cancel",
                            values={"doctype": "Purchase Receipt", "name": old_receipt["name"]},
                        )
                    if corrected is None:
                        corrected = admin.create_document(
                            "Purchase Receipt",
                            {
                                "company": COMPANY,
                                "supplier": supplier,
                                "posting_date": date,
                                "set_posting_time": 1,
                                "currency": "USD",
                                "remarks": tag,
                                "amended_from": old_receipt["name"],
                                "items": [
                                    {
                                        "item_code": item,
                                        "qty": revision["corrected_received_quantity"],
                                        "rate": line["unit_price"],
                                        "uom": "EA",
                                        "purchase_order": po["name"],
                                        "purchase_order_item": po["items"][0]["name"],
                                        "expense_account": EXPENSE,
                                        "cost_center": "Main - IRA",
                                    }
                                ],
                            },
                        )
                    corrected = admin.get_document("Purchase Receipt", corrected["name"])
                    if corrected["docstatus"] == 0:
                        admin.call_method(
                            "frappe.client.submit", values={"doc": json.dumps(corrected)}
                        )
                    sources["corrected_purchase_receipt"] = read_procurement(
                        runtime, "receipt", corrected["name"], "Asia/Jakarta"
                    ).model_dump(mode="json")
                    sources["corrected_purchase_order"] = read_procurement(
                        runtime, "po", po["name"], "Asia/Jakarta"
                    ).model_dump(mode="json")
                    journal["families"][family_id]["corrected_receipt"] = corrected["name"]
                    write(journal_path, journal)
                write(directory / "expected-match.json", matches)
                write(directory / "procurement.json", sources)
                for artifact in family["artifacts"]:
                    artifact["sha256"] = file_digest(pack / artifact["path"])
                write(pack / "manifest.json", manifest)
                print(f"ERP sources bound: {split}/{family_id}", flush=True)
        write(pack / "erp-profile.json", profile)
        audit(pack, inspect_pdf_text=False)
        return {
            "status": "prepared",
            "families": len(journal["families"]),
            "profile": "erp-profile.json",
        }
    finally:
        admin.logout()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--split", choices=("development", "quality_holdout", "time_study"))
    parser.add_argument("--max-families", type=int)
    parser.add_argument("--development-probes", action="store_true")
    parser.add_argument("--development-revisions", action="store_true")
    parser.add_argument("--configure-price-tolerance", action="store_true")
    args = parser.parse_args()
    if args.configure_price_tolerance:
        print(json.dumps(configure_price_policy(args.pack), indent=2))
        return
    if args.max_families is not None and (args.split != "development" or args.max_families < 1):
        raise SystemExit("Only development provisioning may select a subset")
    if (args.development_probes or args.development_revisions) and args.split != "development":
        raise SystemExit("Scenario probes are development only")
    splits = (args.split,) if args.split else ("quality_holdout", "time_study")
    print(
        json.dumps(
            prepare(
                args.pack,
                splits=splits,
                max_families=args.max_families,
                development_probes=args.development_probes,
                development_revisions=args.development_revisions,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
