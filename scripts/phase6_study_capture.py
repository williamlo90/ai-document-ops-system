"""Capture actual study outputs without supplying invoice answers or operator timings."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.benchmark.datasets import load_evaluation_dataset  # noqa: E402
from app.benchmark.service import invoice_data_to_fields  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.core.security import SecurityContext  # noqa: E402
from app.documents.sqlite_store import SqliteStore  # noqa: E402
from app.documents.sqlite_repositories import SqliteDocumentRepository, SqliteExtractionRepository  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.procurement.repository import VersionRepository  # noqa: E402
from app.procurement.service import EvidenceService  # noqa: E402
from app.procurement.matching import MatchService  # noqa: E402
from app.procurement.exceptions import ExceptionService  # noqa: E402
from app.providers.storage import LocalStorageService  # noqa: E402
from phase6_provider_run import attach_provenance  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402


def source_anchors(fields, pdf):
    """Ground entered ERP values against printed tokens, never against oracle labels."""
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    for row in [fields, *fields.get("line_items", [])]:
        row["provenance"] = {
            key: {"kind": "observed", "page": 1, "excerpt": str(value)}
            for key, value in row.items()
            if isinstance(value, str) and value in text
        }
    return fields


def erp_fields(actual, pdf):
    fields = {
        "vendor_name": actual.get("supplier"),
        "invoice_number": actual.get("bill_no"),
        "invoice_date": actual.get("bill_date"),
        "due_date": actual.get("due_date"),
        "currency": actual.get("currency"),
    }
    for field, key in (
        ("subtotal", "net_total"),
        ("tax", "total_taxes_and_charges"),
        ("total", "grand_total"),
    ):
        fields[field] = f"{Decimal(str(actual[key])):.2f}"
    fields["line_items"] = [
        {
            "description": row["description"],
            "uom": row["uom"],
            "quantity": format(Decimal(str(row["qty"])).normalize(), "f"),
            "unit_price": f"{Decimal(str(row['rate'])):.2f}",
            "amount": f"{Decimal(str(row['amount'])):.2f}",
        }
        for row in actual["items"]
    ]
    return source_anchors(fields, pdf)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("document_id")
    parser.add_argument("condition", choices=("manual", "assisted"))
    parser.add_argument("--erp-target")
    parser.add_argument("--app-document-id")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--original-only", action="store_true")
    parser.add_argument(
        "--decision-file",
        type=Path,
        help="Human-authorized manual rejection recorded during the timer",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pack, output = args.pack.resolve(), args.output.resolve()
    if ROOT not in output.parents or "_local_docs" not in output.parts or output.exists():
        raise SystemExit("Capture requires a new ignored local file")
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    document = next(
        d
        for d in load_evaluation_dataset(pack / "time_study").documents
        if d.document_id == args.document_id
    )
    proof = {
        "document_id": document.document_id,
        "condition": args.condition,
        "manifest_sha256": file_digest(pack / "manifest.json"),
        "captured_at": datetime.now(UTC).isoformat(),
    }
    settings = load_settings()
    erp = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        allowed_hosts=settings.erpnext_allowed_hosts,
        timeout_seconds=60,
    )
    if args.erp_target:
        actual = erp.get_purchase_invoice(args.erp_target)
        sources = load_json(document.source_path.parent / "procurement.json")
        prefix = "manual_" if args.condition == "manual" else ""
        po = sources[prefix + "purchase_order"]
        if (
            actual.get("company") != po["company"]
            or actual.get("supplier") != po["supplier_id"]
            or any(row.get("purchase_order") != po["source_id"] for row in actual.get("items", []))
        ):
            raise SystemExit("ERP target is not bound to this study condition")
        proof["erp_readback"] = actual
        proof["ledger_readback"] = (
            erp.get_gl_entries(args.erp_target) if actual["docstatus"] == 1 else []
        )
        proof["predicted_fields"] = erp_fields(actual, document.source_path)
    if args.condition == "assisted":
        if not args.app_document_id or not args.workspace:
            raise SystemExit("Assisted capture requires the isolated workspace and app document ID")
        workspace = args.workspace.resolve()
        binding = load_json(workspace / "binding.json")
        if binding["manifest_sha256"] != proof["manifest_sha256"]:
            raise SystemExit("Workspace belongs to another frozen cohort")
        store = SqliteStore(workspace / "study.db")
        try:
            evidence = EvidenceService(
                VersionRepository(store),
                SqliteDocumentRepository(store),
                SqliteExtractionRepository(store),
            )
            context = SecurityContext(
                "Study evidence collector", role="ap_approver", workspace_id="phase6-human-study"
            )
            app_id = UUID(args.app_document_id)
            saved = evidence.document(app_id, context)
            # Upload filenames must retain the document ID so another invoice cannot be substituted.
            if Path(saved.original_filename).stem != document.document_id:
                raise SystemExit("Study upload filename does not identify the scheduled invoice")
            uploaded = LocalStorageService(workspace / "uploads").open_for_parser(saved.storage_key)
            if file_digest(uploaded) != file_digest(document.source_path):
                raise SystemExit("Uploaded PDF differs from the sealed study source")
            stored = evidence.extractions.get_for_document(app_id).extraction_result
            if args.original_only:
                fields = invoice_data_to_fields(stored.extraction.data)
                attach_provenance(fields, stored.extraction.confidence)
                if evidence.repo.history(context.workspace_id, "invoice", str(app_id)):
                    raise SystemExit("Original capture must precede AP evidence edits")
                if store.query_one(
                    "SELECT 1 FROM correction_events WHERE workspace_id=? AND document_id=? LIMIT 1",
                    (context.workspace_id, str(app_id)),
                ):
                    raise SystemExit("Original capture must precede invoice corrections")
                proof["original_predicted_fields"] = fields
            else:
                revision = evidence.repo.latest(context.workspace_id, "invoice", str(app_id))
                if not revision:
                    raise SystemExit("Final invoice evidence has not been captured")
                fields = {
                    path: value["effective"]
                    for path, value in revision["fields"].items()
                    if not path.startswith("lines.")
                }
                fields["provenance"] = {
                    path: {
                        "kind": value["kind"],
                        "page": value.get("page"),
                        "excerpt": value.get("excerpt"),
                    }
                    for path, value in revision["fields"].items()
                    if not path.startswith("lines.")
                }
                fields["line_items"] = []
                for line_id in revision["line_ids"]:
                    values = {
                        path.split(".", 2)[2]: value
                        for path, value in revision["fields"].items()
                        if path.startswith(f"lines.{line_id}.")
                    }
                    line = {path: value["effective"] for path, value in values.items()}
                    line["provenance"] = {
                        path: {
                            "kind": value["kind"],
                            "page": value.get("page"),
                            "excerpt": value.get("excerpt"),
                        }
                        for path, value in values.items()
                    }
                    fields["line_items"].append(line)
                proof["predicted_fields"] = fields
                match = evidence.repo.latest_for_document(
                    context.workspace_id, "match", str(app_id)
                )
                if (
                    match
                    and MatchService(evidence).status(match["id"], context)["status"] == "rejected"
                ):
                    snapshot = evidence.repo.latest(
                        context.workspace_id, "snapshot", match["snapshot_id"]
                    )
                    request = snapshot["inputs"]["request"]
                    proof["source_refs"] = request["po_ids"] + request["receipt_ids"]
                    proof["dispositions"] = [
                        case
                        for case in ExceptionService(evidence).list_cases(
                            context, document_id=app_id
                        )
                        if case["match_id"] == match["id"] and case["state"] == "rejected"
                    ]
                proof["app_document_id"] = str(app_id)
        finally:
            store.close()
    elif args.decision_file:
        decision = load_json(args.decision_file)
        if (
            decision.get("document_id") != document.document_id
            or decision.get("condition") != "manual"
        ):
            raise SystemExit("Manual decision belongs to another invoice or condition")
        proof["dispositions"] = decision["dispositions"]
        proof["source_refs"] = sorted(
            {ref for row in decision["dispositions"] for ref in row.get("evidence_refs", [])}
        )
    if not args.original_only and not proof.get("predicted_fields"):
        raise SystemExit("No actual final invoice fields captured")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        "Actual study evidence captured; no answers, operator times or success scores were supplied."
    )


if __name__ == "__main__":
    main()
