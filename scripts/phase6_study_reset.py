"""Reset only the first completed synthetic study condition after preserving its readback.

ERP duplicate checking stays enabled. Cancellation/deletion happens outside the
operator timer, allowing the paired condition to use its own untouched PO/receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.benchmark.datasets import load_evaluation_dataset  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402
from phase6_time_study import verify_terminal  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("worksheet", type=Path)
    parser.add_argument("document_id")
    args = parser.parse_args()
    pack = args.pack.resolve()
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    worksheet = load_json(args.worksheet)
    if worksheet["manifest_sha256"] != file_digest(pack / "manifest.json"):
        raise SystemExit("Worksheet does not belong to this cohort")
    pair = next(row for row in worksheet["pairs"] if row["document_id"] == args.document_id)
    first, second = pair["runs"]
    if first.get("elapsed_seconds") is None or second.get("attempt_started_at"):
        raise SystemExit("Reset must follow the first timer and precede the second attempt")
    document = next(
        d
        for d in load_evaluation_dataset(pack / "time_study").documents
        if d.document_id == args.document_id
    )
    reference = first.get("erp_readback_reference")
    if not verify_terminal(
        pack, document, first["condition"], first.get("terminal_outcome"), reference
    ):
        raise SystemExit("Preserve and verify first-condition terminal evidence before reset")
    proof_path = Path(reference).resolve()
    proof = load_json(proof_path)
    reset_path = proof_path.with_suffix(".reset.json")
    if reset_path.exists():
        raise SystemExit("Reset already recorded; do not repeat")
    actual = proof.get("erp_readback")
    if not actual:
        reset_path.write_text(
            json.dumps({"action": "no_remote_target", "proof_sha256": file_digest(proof_path)})
            + "\n"
        )
        print("No ERP target to reset; first condition evidence preserved.")
        return
    settings = load_settings()
    if (
        urlparse(settings.erpnext_base_url).hostname not in {"localhost", "127.0.0.1"}
        or not settings.accounting_sandbox_mode
        or not settings.erpnext_sandbox_posting_enabled
    ):
        raise SystemExit("Explicit local ERP sandbox required")
    admin = ERPNextAdminClient(settings.erpnext_base_url, timeout=60)
    admin.login(_read_env_value(ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"))
    try:
        live = admin.get_document("Purchase Invoice", actual["name"])
        po = pair["procurement_sources"][first["condition"]]["purchase_order"]
        if (
            live.get("modified") != actual.get("modified")
            or live.get("docstatus") != actual.get("docstatus")
            or live.get("company") != "Invoice Review Assisted Benchmark"
            or live.get("supplier") != actual.get("supplier")
            or live.get("bill_no") != actual.get("bill_no")
            or not live.get("items")
            or any(row.get("purchase_order") != po for row in live["items"])
        ):
            raise SystemExit("Target changed or is not the exact synthetic first-condition invoice")
        if live["docstatus"] == 1:
            admin.call_method(
                "frappe.client.cancel", values={"doctype": "Purchase Invoice", "name": live["name"]}
            )
            after = admin.get_document("Purchase Invoice", live["name"])
            if after["docstatus"] != 2:
                raise SystemExit("Cancellation not confirmed")
            action = "cancelled_after_verified_readback"
        elif live["docstatus"] == 0:
            admin.delete_document("Purchase Invoice", live["name"])
            after = None
            action = "draft_deleted_after_capture"
        else:
            raise SystemExit("Only the captured draft or submitted invoice may be reset")
        trace = {
            "at": datetime.now(UTC).isoformat(),
            "action": action,
            "proof_sha256": file_digest(proof_path),
            "target": live["name"],
            "after": after,
            "reason": "Isolate paired synthetic study conditions outside timed work; duplicate guard remains enabled",
        }
        reset_path.write_text(json.dumps(trace, indent=2, default=str) + "\n", encoding="utf-8")
    finally:
        admin.logout()
    print("First-condition target reset; immutable pre-reset invoice/ledger evidence retained.")


if __name__ == "__main__":
    main()
